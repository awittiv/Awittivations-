"""
Train a Faster R-CNN binary sign detector on the CompVis cuneiform dataset.

Strategy: detect sign bounding boxes (class 1 = sign, class 0 = background).
The existing EfficientNet classifier then identifies which sign each crop is.

Usage:
    python ml/train_detector.py

Outputs:
    ml/detector.pt          — best checkpoint
    ml/detector_info.json   — metadata
"""

import ast
import csv
import json
import random
import time
from pathlib import Path

import torch
import torchvision.transforms.functional as TF
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import (
    FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
    fasterrcnn_mobilenet_v3_large_320_fpn,
)
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

ML_DIR = Path(__file__).parent
TABLETS_DIR = ML_DIR / "data" / "tablets"
CSV_FILES = [Path("/tmp/saa05.csv"), Path("/tmp/saa06.csv"), Path("/tmp/saa09.csv")]

MAX_SIZE = 800   # pre-resize tablets to this max dimension before feeding to model
EPOCHS = 15
LR = 5e-4
BATCH_SIZE = 1
VAL_FRAC = 0.15
SEED = 42


# ─────────────────────────────────────────────────────────────────────────────
# Dataset
# ─────────────────────────────────────────────────────────────────────────────

def load_annotations() -> dict[str, list[list[int]]]:
    """Group bounding boxes by P-number. bbox = [x1, y1, x2, y2] in image pixels."""
    annots: dict[str, list] = {}
    for csv_path in CSV_FILES:
        if not csv_path.exists():
            continue
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                pnum = row["tablet_CDLI"]
                bbox = ast.literal_eval(row["bbox"])
                annots.setdefault(pnum, []).append(bbox)
    return annots


class SignDetectionDataset(Dataset):
    def __init__(self, tablets: list[str], annotations: dict, augment: bool = False):
        self.tablets = tablets
        self.annotations = annotations
        self.augment = augment

    def __len__(self) -> int:
        return len(self.tablets)

    def __getitem__(self, idx: int):
        pnum = self.tablets[idx]
        img = Image.open(TABLETS_DIR / f"{pnum}.jpg").convert("RGB")
        w, h = img.size

        # Pre-resize to MAX_SIZE to reduce compute (scale boxes accordingly)
        scale = min(MAX_SIZE / max(w, h), 1.0)
        if scale < 1.0:
            nw, nh = int(w * scale), int(h * scale)
            img = img.resize((nw, nh), Image.LANCZOS)
            w, h = nw, nh
        else:
            scale = 1.0

        raw_boxes = self.annotations.get(pnum, [])
        boxes = []
        for x1, y1, x2, y2 in raw_boxes:
            x1s, y1s, x2s, y2s = x1 * scale, y1 * scale, x2 * scale, y2 * scale
            # Clamp and filter tiny boxes
            x1s = max(0.0, min(x1s, w))
            y1s = max(0.0, min(y1s, h))
            x2s = max(0.0, min(x2s, w))
            y2s = max(0.0, min(y2s, h))
            if x2s - x1s > 3 and y2s - y1s > 3:
                boxes.append([x1s, y1s, x2s, y2s])

        if self.augment and random.random() < 0.5:
            img = TF.hflip(img)
            flipped = []
            for x1, y1, x2, y2 in boxes:
                flipped.append([w - x2, y1, w - x1, y2])
            boxes = flipped

        img_tensor = TF.to_tensor(img)
        n = len(boxes)
        target = {
            "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(n, 4),
            "labels": torch.ones(n, dtype=torch.int64),
        }
        return img_tensor, target


def collate_fn(batch):
    return tuple(zip(*batch))


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation: recall@IoU0.5 on validation tablets
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate(model: torch.nn.Module, loader: DataLoader) -> dict:
    model.eval()
    total_pred, total_gt, total_tp = 0, 0, 0
    score_thresh = 0.5
    iou_thresh = 0.5

    for images, targets in loader:
        outputs = model(list(images))
        for out, tgt in zip(outputs, targets):
            gt_boxes = tgt["boxes"]
            scores = out["scores"]
            pred_boxes = out["boxes"][scores >= score_thresh]

            total_gt += gt_boxes.shape[0]
            total_pred += pred_boxes.shape[0]

            if gt_boxes.shape[0] == 0 or pred_boxes.shape[0] == 0:
                continue

            from torchvision.ops import box_iou
            iou_mat = box_iou(pred_boxes, gt_boxes)   # [P, G]
            matched_gt = (iou_mat.max(dim=0).values >= iou_thresh).sum().item()
            total_tp += matched_gt

    recall = total_tp / total_gt if total_gt else 0.0
    precision = total_tp / total_pred if total_pred else 0.0
    return {
        "recall": recall,
        "precision": precision,
        "total_pred": total_pred,
        "total_gt": total_gt,
        "total_tp": total_tp,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    annotations = load_annotations()
    all_tablets = sorted(t for t in annotations if (TABLETS_DIR / f"{t}.jpg").exists())

    random.seed(SEED)
    random.shuffle(all_tablets)
    n_val = max(1, round(len(all_tablets) * VAL_FRAC))
    val_tablets = all_tablets[:n_val]
    train_tablets = all_tablets[n_val:]

    n_train_boxes = sum(len(annotations[t]) for t in train_tablets)
    n_val_boxes = sum(len(annotations[t]) for t in val_tablets)
    print(f"Train: {len(train_tablets)} tablets, {n_train_boxes} annotations")
    print(f"Val:   {len(val_tablets)} tablets, {n_val_boxes} annotations")

    train_ds = SignDetectionDataset(train_tablets, annotations, augment=True)
    val_ds = SignDetectionDataset(val_tablets, annotations, augment=False)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              collate_fn=collate_fn, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=1, shuffle=False,
                            collate_fn=collate_fn, num_workers=0)

    device = torch.device("cpu")

    weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
    model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights)

    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes=2)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    best_loss = float("inf")
    best_epoch = 0
    history = []

    print(f"\nTraining Faster R-CNN detector for {EPOCHS} epochs on CPU…\n")

    for epoch in range(1, EPOCHS + 1):
        model.train()
        epoch_loss = 0.0
        t0 = time.time()

        for images, targets in train_loader:
            images = list(images)
            targets = list(targets)
            loss_dict = model(images, targets)
            loss = sum(loss_dict.values())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        scheduler.step()
        epoch_loss /= len(train_loader)
        elapsed = time.time() - t0

        row = {"epoch": epoch, "loss": round(epoch_loss, 4), "seconds": round(elapsed, 1)}
        history.append(row)
        print(f"Epoch {epoch:2d}/{EPOCHS}  loss={epoch_loss:.4f}  lr={scheduler.get_last_lr()[0]:.2e}  {elapsed:.0f}s")

        if epoch_loss < best_loss:
            best_loss = epoch_loss
            best_epoch = epoch
            torch.save(model.state_dict(), ML_DIR / "detector.pt")
            print("           ↑ new best checkpoint saved")

    print("\nRunning validation evaluation…")
    # Reload best checkpoint for eval
    model.load_state_dict(torch.load(ML_DIR / "detector.pt", map_location="cpu", weights_only=True))
    val_metrics = evaluate(model, val_loader)
    print(f"Val recall@IoU0.5: {val_metrics['recall']:.3f}")
    print(f"Val precision:     {val_metrics['precision']:.3f}")
    print(f"TP/GT/Pred:        {val_metrics['total_tp']}/{val_metrics['total_gt']}/{val_metrics['total_pred']}")

    info = {
        "type": "faster_rcnn_mobilenet_v3_320",
        "n_classes": 2,
        "max_size": MAX_SIZE,
        "best_train_loss": round(best_loss, 4),
        "best_epoch": best_epoch,
        "val_recall": round(val_metrics["recall"], 4),
        "val_precision": round(val_metrics["precision"], 4),
        "train_tablets": train_tablets,
        "val_tablets": val_tablets,
        "history": history,
    }
    (ML_DIR / "detector_info.json").write_text(json.dumps(info, indent=2))
    print("\nDetector saved → ml/detector.pt")
    print("Info saved     → ml/detector_info.json")


if __name__ == "__main__":
    main()
