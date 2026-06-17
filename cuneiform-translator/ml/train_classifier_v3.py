"""
Classifier v3: EfficientNet-B2 + mixup + label smoothing + class weighting.

Improvements over v2:
- EfficientNet-B2 backbone (9.1M vs 5.3M params)
- Mixup: lam*loss(pred, labels_a) + (1-lam)*loss(pred, labels_b) — one forward pass
- Label smoothing: CrossEntropyLoss(label_smoothing=0.1)
- Class-weighted loss: inverse-frequency weights penalize ignoring rare signs
- Elastic distortion augmentation for wedge-shape variants

Usage:
    python ml/train_classifier_v3.py [--epochs N] [--batch-size N]

Outputs:
    ml/model.pt
    ml/model_info.json  (backbone field for inference routing)
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import ConcatDataset, DataLoader, Dataset, random_split
from torchvision import models, transforms

ML_DIR        = Path(__file__).parent
GT_CROPS_DIR  = ML_DIR / "data" / "crops"
DET_CROPS_DIR = ML_DIR / "data" / "detector_crops"
LABEL_MAP_PATH = ML_DIR / "label_map.json"
MODEL_PATH    = ML_DIR / "model.pt"
INFO_PATH     = ML_DIR / "model_info.json"

CROP_SIZE = 64
BACKBONE  = "efficientnet_b2"


def get_transforms(train: bool):
    if train:
        return transforms.Compose([
            transforms.Resize((CROP_SIZE + 16, CROP_SIZE + 16)),
            transforms.RandomCrop(CROP_SIZE),
            transforms.RandomHorizontalFlip(p=0.3),
            transforms.RandomRotation(20),
            transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.2),
            transforms.RandomGrayscale(p=0.1),
            transforms.ElasticTransform(alpha=30.0, sigma=4.0),
            transforms.Resize((CROP_SIZE, CROP_SIZE)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize((CROP_SIZE, CROP_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


class CropDataset(Dataset):
    def __init__(self, root: Path, folder_to_idx: dict[str, int], transform):
        self.samples: list[tuple[Path, int]] = []
        self.transform = transform
        for class_dir in sorted(root.iterdir()):
            if not class_dir.is_dir() or class_dir.name not in folder_to_idx:
                continue
            label = folder_to_idx[class_dir.name]
            for img_path in sorted(class_dir.glob("*.jpg")):
                self.samples.append((img_path, label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        return self.transform(img), label


def build_model(n_classes: int) -> nn.Module:
    model = models.efficientnet_b2(weights=models.EfficientNet_B2_Weights.DEFAULT)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, n_classes),
    )
    return model


def compute_class_weights(dataset: ConcatDataset, n_classes: int) -> torch.Tensor:
    counts = torch.zeros(n_classes)
    for ds in dataset.datasets:
        for _, label in ds.samples:
            counts[label] += 1
    counts = counts.clamp(min=1)
    weights = 1.0 / counts
    weights = weights / weights.sum() * n_classes  # normalize to mean=1
    return weights


def train_epoch(model, loader, criterion, optimizer, device, alpha: float = 0.4):
    model.train()
    total_loss = correct = total = 0
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)
        lam = float(np.random.beta(alpha, alpha))
        idx = torch.randperm(imgs.size(0), device=device)
        mixed = lam * imgs + (1 - lam) * imgs[idx]

        optimizer.zero_grad()
        out = model(mixed)
        # One forward pass; split mixup loss properly (preserves class weights)
        loss = lam * criterion(out, labels) + (1 - lam) * criterion(out, labels[idx])
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * len(labels)
        correct += (out.argmax(1) == labels).sum().item()
        total += len(labels)
    return total_loss / total, correct / total


@torch.no_grad()
def eval_epoch(model, loader, criterion, device):
    model.eval()
    total_loss = correct = total = 0
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)
        out = model(imgs)
        loss = criterion(out, labels)
        total_loss += loss.item() * len(labels)
        correct += (out.argmax(1) == labels).sum().item()
        total += len(labels)
    return total_loss / total, correct / total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--val-frac", type=float, default=0.15)
    parser.add_argument("--mixup-alpha", type=float, default=0.4)
    args = parser.parse_args()

    label_map = json.loads(LABEL_MAP_PATH.read_text())
    train_label_to_class: dict[str, int] = label_map["train_label_to_class"]
    n_classes = label_map["n_classes"]

    # GT crop dirs are named by sequential class index
    gt_folders = sorted(
        [d.name for d in GT_CROPS_DIR.iterdir() if d.is_dir()],
        key=lambda x: int(x)
    )
    folder_to_idx = {name: i for i, name in enumerate(gt_folders)}
    n_classes = len(gt_folders)
    print(f"Classes: {n_classes}")

    train_tf = get_transforms(train=True)

    gt_ds = CropDataset(GT_CROPS_DIR, folder_to_idx, train_tf)
    print(f"GT crops: {len(gt_ds)}")

    datasets_to_merge = [gt_ds]
    if DET_CROPS_DIR.exists():
        tl_to_folder = {tl: str(ci) for tl, ci in train_label_to_class.items()}
        det_folder_to_idx = {
            tl: folder_to_idx[ci_str]
            for tl, ci_str in tl_to_folder.items()
            if ci_str in folder_to_idx
        }
        det_ds = CropDataset(DET_CROPS_DIR, det_folder_to_idx, train_tf)
        print(f"Detector crops: {len(det_ds)}")
        datasets_to_merge.append(det_ds)

    full_ds = ConcatDataset(datasets_to_merge)
    print(f"Total: {len(full_ds)} samples")

    n_val   = max(1, round(len(full_ds) * args.val_frac))
    n_train = len(full_ds) - n_val
    train_ds, val_ds = random_split(
        full_ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size, shuffle=False,
                              num_workers=0, pin_memory=False)

    device = torch.device("cpu")
    model  = build_model(n_classes).to(device)

    # Class weights from full dataset (train+val combined for weight estimation)
    class_weights = compute_class_weights(full_ds, n_classes).to(device)
    print(f"Class weight range: {class_weights.min():.3f} – {class_weights.max():.3f}")

    criterion_train = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.1)
    criterion_val   = nn.CrossEntropyLoss()

    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_acc = 0.0
    history = []

    print(f"\nTraining {BACKBONE} for {args.epochs} epochs "
          f"(mixup α={args.mixup_alpha}, label_smoothing=0.1, class_weighted=True)…\n")

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        tr_loss, tr_acc = train_epoch(
            model, train_loader, criterion_train, optimizer, device, args.mixup_alpha
        )
        val_loss, val_acc = eval_epoch(model, val_loader, criterion_val, device)
        scheduler.step()
        elapsed = time.time() - t0
        print(f"Epoch {epoch:2d}/{args.epochs}  "
              f"tr_loss={tr_loss:.4f}  tr_acc={tr_acc:.3f}  "
              f"val_loss={val_loss:.4f}  val_acc={val_acc:.3f}  {elapsed:.0f}s")
        history.append({"epoch": epoch, "tr_acc": round(tr_acc, 4), "val_acc": round(val_acc, 4)})
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), MODEL_PATH)
            print(f"           ↑ saved (val_acc={val_acc:.4f})")

    info = {
        "backbone": BACKBONE,
        "n_classes": n_classes,
        "class_to_idx": folder_to_idx,
        "best_val_acc": best_val_acc,
        "crop_size": CROP_SIZE,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "n_train": n_train,
        "n_val": n_val,
        "detector_crops_used": DET_CROPS_DIR.exists(),
        "mixup_alpha": args.mixup_alpha,
        "label_smoothing": 0.1,
        "class_weighted": True,
        "history": history,
    }
    INFO_PATH.write_text(json.dumps(info, indent=2))
    print(f"\nBest val acc: {best_val_acc:.4f} → {MODEL_PATH}")


if __name__ == "__main__":
    main()
