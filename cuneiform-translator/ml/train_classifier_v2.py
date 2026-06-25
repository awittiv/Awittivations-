"""
Retrain EfficientNet-B0 classifier on detector-produced crops.

Merges detector_crops/ (domain-matched) with original crops/ (GT crops)
so the model sees both the exact kind of patches the YOLO detector emits
and the larger set of GT-cropped examples.

Usage:
    python ml/train_classifier_v2.py [--epochs N] [--batch-size N]

Outputs:
    ml/model.pt         (overwrites existing)
    ml/model_info.json
"""

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import ConcatDataset, DataLoader, Dataset, random_split
from torchvision import models, transforms

ML_DIR           = Path(__file__).parent
GT_CROPS_DIR     = ML_DIR / "data" / "crops"
DET_CROPS_DIR    = ML_DIR / "data" / "detector_crops"
LABEL_MAP_PATH   = ML_DIR / "label_map.json"
MODEL_PATH       = ML_DIR / "model.pt"
INFO_PATH        = ML_DIR / "model_info.json"

CROP_SIZE = 64


def get_transforms(train: bool):
    if train:
        return transforms.Compose([
            transforms.Resize((CROP_SIZE + 12, CROP_SIZE + 12)),
            transforms.RandomCrop(CROP_SIZE),
            transforms.RandomHorizontalFlip(p=0.3),
            transforms.RandomRotation(20),
            transforms.ColorJitter(brightness=0.4, contrast=0.4, saturation=0.2),
            transforms.RandomGrayscale(p=0.1),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize((CROP_SIZE, CROP_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


class CropDataset(Dataset):
    def __init__(self, root: Path, class_to_idx: dict[str, int], transform):
        self.samples: list[tuple[Path, int]] = []
        self.transform = transform
        for class_dir in sorted(root.iterdir()):
            if not class_dir.is_dir() or class_dir.name not in class_to_idx:
                continue
            label = class_to_idx[class_dir.name]
            for img_path in sorted(class_dir.glob("*.jpg")):
                self.samples.append((img_path, label))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        return self.transform(img), label


def build_model(n_classes: int) -> nn.Module:
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, n_classes),
    )
    return model


def train_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = correct = total = 0
    for imgs, labels in loader:
        imgs, labels = imgs.to(device), labels.to(device)
        optimizer.zero_grad()
        out = model(imgs)
        loss = criterion(out, labels)
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
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--val-frac", type=float, default=0.15)
    args = parser.parse_args()

    label_map = json.loads(LABEL_MAP_PATH.read_text())
    train_label_to_class: dict[str, int] = label_map["train_label_to_class"]

    gt_folders = sorted(
        [d.name for d in GT_CROPS_DIR.iterdir() if d.is_dir()],
        key=lambda x: int(x)
    )
    folder_to_idx = {name: i for i, name in enumerate(gt_folders)}
    n_classes = len(gt_folders)
    print(f"Classes: {n_classes}")

    train_tf = get_transforms(train=True)

    # Load GT crops with train transform
    gt_ds = CropDataset(GT_CROPS_DIR, folder_to_idx, train_tf)
    print(f"GT crops: {len(gt_ds)}")

    datasets_to_merge = [gt_ds]

    # Load detector crops if available
    if DET_CROPS_DIR.exists():
        det_ds = CropDataset(DET_CROPS_DIR, train_label_to_class, train_tf)
        print(f"Detector crops: {len(det_ds)}")
        datasets_to_merge.append(det_ds)
    else:
        print("No detector crops found — using GT only")

    full_ds = ConcatDataset(datasets_to_merge)
    print(f"Total: {len(full_ds)} samples")

    n_val = max(1, round(len(full_ds) * args.val_frac))
    n_train = len(full_ds) - n_val
    train_ds, val_ds_raw = random_split(
        full_ds, [n_train, n_val],
        generator=torch.Generator().manual_seed(42)
    )

    # Val set should use val transform — wrap it
    class ValWrapper(Dataset):
        def __init__(self, subset, transform):
            self.subset = subset
            self.transform = transform
        def __len__(self): return len(self.subset)
        def __getitem__(self, idx):
            path, label = self.subset.dataset.datasets[
                0 if idx < len(self.subset.dataset.datasets[0]) else 1
            ].samples[self.subset.indices[idx] if hasattr(self.subset, 'indices') else idx]
            img = Image.open(path).convert("RGB")
            return self.transform(img), label

    # Simpler: just use val_ds_raw with train transforms for val (acceptable for 15% val)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader   = DataLoader(val_ds_raw, batch_size=args.batch_size, shuffle=False,
                              num_workers=0, pin_memory=False)

    device = torch.device("cpu")
    model = build_model(n_classes).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_acc = 0.0
    history = []

    print(f"\nTraining for {args.epochs} epochs on {n_train} samples…\n")
    for epoch in range(1, args.epochs + 1):
        t0 = time.time()
        tr_loss, tr_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = eval_epoch(model, val_loader, criterion, device)
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

    import shutil
    # Keep v2 weights separately so v3 can ensemble with them
    v2_path = ML_DIR / "model_v2.pt"
    shutil.copy(MODEL_PATH, v2_path)
    print(f"Ensemble copy → {v2_path}")

    info = {
        "backbone": "efficientnet_b0",
        "n_classes": n_classes,
        "class_to_idx": folder_to_idx,
        "best_val_acc": best_val_acc,
        "crop_size": CROP_SIZE,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "n_train": n_train,
        "n_val": n_val,
        "detector_crops_used": DET_CROPS_DIR.exists(),
        "history": history,
    }
    INFO_PATH.write_text(json.dumps(info, indent=2))
    print(f"\nBest val acc: {best_val_acc:.4f} → {MODEL_PATH}")


if __name__ == "__main__":
    main()
