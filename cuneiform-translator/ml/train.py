"""
Fine-tune EfficientNet-B0 on cuneiform sign crops.

Usage: python3 train.py [--epochs N] [--batch-size N]
Outputs: ml/model.pt  (full model)  +  ml/model_info.json
"""

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn as nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader, random_split
from torchvision import datasets, models, transforms

CROPS_DIR  = Path(__file__).parent / "data" / "crops"
MODEL_PATH = Path(__file__).parent / "model.pt"
INFO_PATH  = Path(__file__).parent / "model_info.json"
CROP_SIZE  = 64


def get_transforms(train: bool):
    if train:
        return transforms.Compose([
            transforms.Resize((CROP_SIZE + 8, CROP_SIZE + 8)),
            transforms.RandomCrop(CROP_SIZE),
            transforms.RandomHorizontalFlip(p=0.3),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.3, contrast=0.3),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize((CROP_SIZE, CROP_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225]),
    ])


def build_model(n_classes: int) -> nn.Module:
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
    # Replace classifier head
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
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--val-split", type=float, default=0.15)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Load full dataset with training transforms first to get class info
    full_ds = datasets.ImageFolder(CROPS_DIR, transform=get_transforms(True))
    n_classes = len(full_ds.classes)
    print(f"Classes: {n_classes} | Total images: {len(full_ds)}")

    # Train/val split
    n_val = int(len(full_ds) * args.val_split)
    n_train = len(full_ds) - n_val
    train_ds, val_ds = random_split(full_ds, [n_train, n_val],
                                    generator=torch.Generator().manual_seed(42))

    # Val subset gets inference transforms
    val_ds.dataset = datasets.ImageFolder(CROPS_DIR, transform=get_transforms(False))

    train_loader = DataLoader(train_ds, batch_size=args.batch_size,
                              shuffle=True, num_workers=2, pin_memory=False)
    val_loader   = DataLoader(val_ds,   batch_size=args.batch_size,
                              shuffle=False, num_workers=2, pin_memory=False)

    model = build_model(n_classes).to(device)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    optimizer = AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-6)

    print(f"\nTraining EfficientNet-B0  |  {n_train} train  {n_val} val  |  {args.epochs} epochs")
    print("-" * 65)

    best_val_acc = 0.0
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        tr_loss, tr_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        va_loss, va_acc = eval_epoch(model, val_loader, criterion, device)
        scheduler.step()

        marker = " *" if va_acc > best_val_acc else ""
        if va_acc > best_val_acc:
            best_val_acc = va_acc
            torch.save(model.state_dict(), MODEL_PATH)

        elapsed = time.time() - t0
        eta = elapsed / epoch * (args.epochs - epoch)
        print(f"Epoch {epoch:3d}/{args.epochs}  "
              f"loss {tr_loss:.3f}/{va_loss:.3f}  "
              f"acc {tr_acc:.3f}/{va_acc:.3f}  "
              f"ETA {eta/60:.1f}m{marker}")

    print(f"\nBest val accuracy: {best_val_acc:.3f}")
    print(f"Model saved to: {MODEL_PATH}")

    # Save metadata for inference
    info = {
        "n_classes": n_classes,
        "classes": full_ds.classes,         # folder names (= compact class indices as strings)
        "class_to_idx": full_ds.class_to_idx,
        "crop_size": CROP_SIZE,
        "best_val_acc": best_val_acc,
    }
    INFO_PATH.write_text(json.dumps(info, indent=2))
    print(f"Model info saved to: {INFO_PATH}")


if __name__ == "__main__":
    main()
