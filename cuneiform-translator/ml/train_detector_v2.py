"""
Faster R-CNN detector v2: tiled training for better small-sign recall.

Each tablet is split into overlapping 512x512 patches (75% overlap).
This multiplies training examples ~16x and makes signs larger relative
to the patch, dramatically improving detection recall.

Usage:
    python ml/train_detector_v2.py

Outputs:
    ml/detector.pt          (overwrites v1)
    ml/detector_info.json
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

TILE_SIZE = 512          # patch size
TILE_STRIDE = 256        # 50% overlap (512 * 0.5)
RESIZE_MAX = 1200        # pre-scale tablets to this before tiling
EPOCHS = 30
LR = 3e-5                # conservative LR — previous 2e-4 caused loss explosion
WARMUP_EPOCHS = 3        # linear warmup before cosine decay
GRAD_CLIP = 10.0         # gradient norm clip to prevent instability
BATCH_SIZE = 2
VAL_FRAC = 0.15          # holdout by tablet (not by tile)
SEED = 42
MIN_BOX_SIZE = 8         # discard tiny boxes after tile crop


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def load_annotations() -> dict[str, list[list[int]]]:
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


def make_tiles(pnum: str, annots: dict, augment: bool = False) -> list[dict]:
    """
    Tile a tablet image into overlapping TILE_SIZE x TILE_SIZE patches.
    Returns list of {image: tensor, boxes: tensor, labels: tensor}.
    """
    img_path = TABLETS_DIR / f"{pnum}.jpg"
    img = Image.open(img_path).convert("RGB")
    w, h = img.size

    # Pre-scale to RESIZE_MAX
    scale = min(RESIZE_MAX / max(w, h), 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
    else:
        scale = 1.0

    # Scale annotations
    raw_boxes = annots.get(pnum, [])
    boxes_scaled = [[x1 * scale, y1 * scale, x2 * scale, y2 * scale] for x1, y1, x2, y2 in raw_boxes]

    tiles = []
    ys = list(range(0, max(1, h - TILE_SIZE), TILE_STRIDE)) + [max(0, h - TILE_SIZE)]
    xs = list(range(0, max(1, w - TILE_SIZE), TILE_STRIDE)) + [max(0, w - TILE_SIZE)]
    ys = sorted(set(ys))
    xs = sorted(set(xs))

    for y0 in ys:
        y1 = min(y0 + TILE_SIZE, h)
        for x0 in xs:
            x1 = min(x0 + TILE_SIZE, w)

            # Collect boxes that overlap this tile (center must be inside)
            tile_boxes = []
            for bx1, by1, bx2, by2 in boxes_scaled:
                cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
                if x0 <= cx <= x1 and y0 <= cy <= y1:
                    # Clip to tile
                    nbx1 = max(bx1, x0) - x0
                    nby1 = max(by1, y0) - y0
                    nbx2 = min(bx2, x1) - x0
                    nby2 = min(by2, y1) - y0
                    if nbx2 - nbx1 >= MIN_BOX_SIZE and nby2 - nby1 >= MIN_BOX_SIZE:
                        tile_boxes.append([nbx1, nby1, nbx2, nby2])

            if not tile_boxes:
                continue  # skip empty tiles

            patch = img.crop((x0, y0, x1, y1))
            pw, ph = patch.size

            # Augment: horizontal flip
            if augment and random.random() < 0.5:
                patch = patch.transpose(Image.FLIP_LEFT_RIGHT)
                tile_boxes = [[pw - b[2], b[1], pw - b[0], b[3]] for b in tile_boxes]

            img_t = TF.to_tensor(patch)
            n = len(tile_boxes)
            target = {
                "boxes": torch.tensor(tile_boxes, dtype=torch.float32).reshape(n, 4),
                "labels": torch.ones(n, dtype=torch.int64),
            }
            tiles.append((img_t, target))

    return tiles


class TiledDataset(Dataset):
    def __init__(self, tablets: list[str], annotations: dict, augment: bool = False):
        self.tiles = []
        for pnum in tablets:
            self.tiles.extend(make_tiles(pnum, annotations, augment=augment))

    def __len__(self) -> int:
        return len(self.tiles)

    def __getitem__(self, idx: int):
        return self.tiles[idx]


def collate_fn(batch):
    return tuple(zip(*batch))


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def evaluate_tablet(model: torch.nn.Module, pnum: str, annotations: dict, score_thresh: float = 0.3) -> dict:
    """Whole-tablet evaluation — slides over tiles and collects predictions."""
    from torchvision.ops import box_iou, nms

    img_path = TABLETS_DIR / f"{pnum}.jpg"
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    scale = min(RESIZE_MAX / max(w, h), 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size
    else:
        scale = 1.0

    ys = list(range(0, max(1, h - TILE_SIZE), TILE_STRIDE)) + [max(0, h - TILE_SIZE)]
    xs = list(range(0, max(1, w - TILE_SIZE), TILE_STRIDE)) + [max(0, w - TILE_SIZE)]
    ys = sorted(set(ys))
    xs = sorted(set(xs))

    all_boxes, all_scores = [], []
    model.eval()
    for y0 in ys:
        y1 = min(y0 + TILE_SIZE, h)
        for x0 in xs:
            x1 = min(x0 + TILE_SIZE, w)
            patch = img.crop((x0, y0, x1, y1))
            img_t = TF.to_tensor(patch)
            out = model([img_t])[0]
            for box, score in zip(out["boxes"], out["scores"]):
                if score.item() >= score_thresh:
                    x1b, y1b, x2b, y2b = box.tolist()
                    all_boxes.append([x1b + x0, y1b + y0, x2b + x0, y2b + y0])
                    all_scores.append(score.item())

    if not all_boxes:
        return {"n_pred": 0, "n_gt": len(annotations.get(pnum, []))}

    boxes_t = torch.tensor(all_boxes, dtype=torch.float32)
    scores_t = torch.tensor(all_scores)
    keep = nms(boxes_t, scores_t, iou_threshold=0.3)
    pred_boxes = boxes_t[keep]

    gt_raw = annotations.get(pnum, [])
    gt_boxes = torch.tensor([[x1 * scale, y1 * scale, x2 * scale, y2 * scale]
                              for x1, y1, x2, y2 in gt_raw], dtype=torch.float32)

    if gt_boxes.shape[0] == 0:
        return {"n_pred": pred_boxes.shape[0], "n_gt": 0}

    iou_mat = box_iou(pred_boxes, gt_boxes)
    tp = (iou_mat.max(dim=0).values >= 0.5).sum().item()
    return {"n_pred": pred_boxes.shape[0], "n_gt": gt_boxes.shape[0], "tp": tp}


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

    print(f"Train: {len(train_tablets)} tablets, Val: {len(val_tablets)} tablets")
    print(f"Preparing tiled dataset (tile={TILE_SIZE}, stride={TILE_STRIDE})…")
    t0 = time.time()
    train_ds = TiledDataset(train_tablets, annotations, augment=True)
    print(f"Train tiles: {len(train_ds)} (took {time.time()-t0:.0f}s)")

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              collate_fn=collate_fn, num_workers=0)

    device = torch.device("cpu")

    weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
    model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes=2)
    model.to(device)

    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=1e-4)
    warmup = torch.optim.lr_scheduler.LinearLR(
        optimizer, start_factor=0.1, end_factor=1.0, total_iters=WARMUP_EPOCHS
    )
    cosine = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=EPOCHS - WARMUP_EPOCHS
    )
    scheduler = torch.optim.lr_scheduler.SequentialLR(
        optimizer, schedulers=[warmup, cosine], milestones=[WARMUP_EPOCHS]
    )

    best_loss = float("inf")
    history = []

    print(f"\nTraining detector v2 for {EPOCHS} epochs on {len(train_ds)} tiles…\n")

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
            torch.nn.utils.clip_grad_norm_(params, max_norm=GRAD_CLIP)
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
            torch.save(model.state_dict(), ML_DIR / "detector.pt")
            print("           ↑ new best checkpoint saved")

    print("\nRunning whole-tablet validation evaluation…")
    model.load_state_dict(torch.load(ML_DIR / "detector.pt", map_location="cpu", weights_only=True))
    total_pred, total_gt, total_tp = 0, 0, 0
    for pnum in val_tablets:
        stats = evaluate_tablet(model, pnum, annotations, score_thresh=0.3)
        tp = stats.get("tp", 0)
        total_pred += stats["n_pred"]
        total_gt += stats["n_gt"]
        total_tp += tp
        recall = tp / stats["n_gt"] if stats["n_gt"] else 0
        print(f"  {pnum}: pred={stats['n_pred']}, gt={stats['n_gt']}, tp={tp}, recall={recall:.2f}")

    val_recall = total_tp / total_gt if total_gt else 0.0
    val_precision = total_tp / total_pred if total_pred else 0.0
    print(f"\nOverall: recall={val_recall:.3f}, precision={val_precision:.3f}")

    info = {
        "type": "faster_rcnn_mobilenet_v3_320_tiled",
        "n_classes": 2,
        "tile_size": TILE_SIZE,
        "tile_stride": TILE_STRIDE,
        "resize_max": RESIZE_MAX,
        "eval_score_thresh": 0.3,
        "best_train_loss": round(best_loss, 4),
        "val_recall": round(val_recall, 4),
        "val_precision": round(val_precision, 4),
        "train_tablets": train_tablets,
        "val_tablets": val_tablets,
        "n_train_tiles": len(train_ds),
        "history": history,
    }
    (ML_DIR / "detector_info.json").write_text(json.dumps(info, indent=2))
    print("\nDetector v2 saved → ml/detector.pt")


if __name__ == "__main__":
    main()
