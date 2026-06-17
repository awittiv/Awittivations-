"""
YOLOv8 sign detector training.

Tiles each tablet into overlapping 512x512 patches, converts CompVis
bounding box annotations to YOLO format, then trains YOLOv8n.

Usage:
    python ml/train_yolo.py

Outputs:
    ml/yolo_dataset/          (tiled images + labels)
    ml/yolo_runs/detect/      (Ultralytics run directory)
    ml/detector_yolo.pt       (best weights, copied out)
    ml/detector_info.json     (updated)
"""

import ast
import csv
import json
import random
import shutil
from pathlib import Path

from PIL import Image

ML_DIR = Path(__file__).parent
TABLETS_DIR = ML_DIR / "data" / "tablets"
DATASET_DIR = ML_DIR / "yolo_dataset"
CSV_FILES = [Path("/tmp/saa05.csv"), Path("/tmp/saa06.csv"), Path("/tmp/saa09.csv")]

TILE_SIZE = 512
TILE_STRIDE = 256
RESIZE_MAX = 1200
MIN_BOX_PX = 8
VAL_FRAC = 0.15
SEED = 42
EPOCHS = 50
BATCH = 4
IMGSZ = 512
MODEL = "yolov8n.pt"


# ─────────────────────────────────────────────────────────────────────────────
# Dataset preparation
# ─────────────────────────────────────────────────────────────────────────────

def load_annotations() -> dict[str, list]:
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


def tile_tablet(pnum: str, annots: dict, split: str) -> int:
    img_path = TABLETS_DIR / f"{pnum}.jpg"
    img = Image.open(img_path).convert("RGB")
    w, h = img.size

    scale = min(RESIZE_MAX / max(w, h), 1.0)
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size

    boxes_scaled = [
        [x1 * scale, y1 * scale, x2 * scale, y2 * scale]
        for x1, y1, x2, y2 in annots.get(pnum, [])
    ]

    img_dir = DATASET_DIR / "images" / split
    lbl_dir = DATASET_DIR / "labels" / split
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    ys = sorted(set(list(range(0, max(1, h - TILE_SIZE), TILE_STRIDE)) + [max(0, h - TILE_SIZE)]))
    xs = sorted(set(list(range(0, max(1, w - TILE_SIZE), TILE_STRIDE)) + [max(0, w - TILE_SIZE)]))

    n_saved = 0
    for y0 in ys:
        y1 = min(y0 + TILE_SIZE, h)
        for x0 in xs:
            x1 = min(x0 + TILE_SIZE, w)
            pw, ph = x1 - x0, y1 - y0

            tile_labels = []
            for bx1, by1, bx2, by2 in boxes_scaled:
                cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
                if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                    continue
                nbx1 = max(bx1, x0) - x0
                nby1 = max(by1, y0) - y0
                nbx2 = min(bx2, x1) - x0
                nby2 = min(by2, y1) - y0
                if nbx2 - nbx1 < MIN_BOX_PX or nby2 - nby1 < MIN_BOX_PX:
                    continue
                # YOLO: class cx cy w h  (normalized)
                ycx = ((nbx1 + nbx2) / 2) / pw
                ycy = ((nby1 + nby2) / 2) / ph
                yw = (nbx2 - nbx1) / pw
                yh = (nby2 - nby1) / ph
                tile_labels.append(f"0 {ycx:.6f} {ycy:.6f} {yw:.6f} {yh:.6f}")

            if not tile_labels:
                continue

            stem = f"{pnum}_{x0}_{y0}"
            patch = img.crop((x0, y0, x1, y1))
            patch.save(img_dir / f"{stem}.jpg", quality=92)
            (lbl_dir / f"{stem}.txt").write_text("\n".join(tile_labels))
            n_saved += 1

    return n_saved


def build_dataset(annotations: dict) -> tuple[list, list, int]:
    tablets = sorted(t for t in annotations if (TABLETS_DIR / f"{t}.jpg").exists())
    random.seed(SEED)
    random.shuffle(tablets)
    n_val = max(1, round(len(tablets) * VAL_FRAC))
    val_tablets = tablets[:n_val]
    train_tablets = tablets[n_val:]

    # Wipe and rebuild
    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)

    print(f"Tiling {len(train_tablets)} train tablets…")
    n_train = sum(tile_tablet(p, annotations, "train") for p in train_tablets)
    print(f"Tiling {len(val_tablets)} val tablets…")
    n_val_tiles = sum(tile_tablet(p, annotations, "val") for p in val_tablets)
    print(f"Train tiles: {n_train}  Val tiles: {n_val_tiles}")

    data_yaml = {
        "path": str(DATASET_DIR.resolve()),
        "train": "images/train",
        "val": "images/val",
        "nc": 1,
        "names": ["sign"],
    }
    yaml_path = DATASET_DIR / "data.yaml"
    # Write as plain text so PyYAML isn't needed
    yaml_path.write_text(
        f"path: {data_yaml['path']}\n"
        f"train: {data_yaml['train']}\n"
        f"val: {data_yaml['val']}\n"
        f"nc: {data_yaml['nc']}\n"
        f"names: {data_yaml['names']}\n"
    )
    return train_tablets, val_tablets, n_train


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import torch
    from ultralytics import YOLO

    annotations = load_annotations()
    train_tablets, val_tablets, n_train = build_dataset(annotations)

    print(f"\nTraining YOLOv8n for {EPOCHS} epochs on {n_train} tiles…")

    runs_dir = ML_DIR / "yolo_runs"
    model = YOLO(MODEL)
    results = model.train(
        data=str(DATASET_DIR / "data.yaml"),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        device="cpu",
        project=str(runs_dir),
        name="detect",
        exist_ok=True,
        # Augmentation
        flipud=0.0,
        fliplr=0.5,
        degrees=5.0,
        translate=0.1,
        scale=0.3,
        mosaic=0.5,
        # Disable workers on CPU-only to avoid memory pressure
        workers=0,
        verbose=True,
    )

    # Copy best weights to a stable path
    best = runs_dir / "detect" / "weights" / "best.pt"
    dest = ML_DIR / "detector_yolo.pt"
    shutil.copy(best, dest)
    print(f"\nBest weights → {dest}")

    # Validate
    val_model = YOLO(str(dest))
    metrics = val_model.val(
        data=str(DATASET_DIR / "data.yaml"),
        imgsz=IMGSZ,
        device="cpu",
        workers=0,
        verbose=False,
    )
    map50 = float(metrics.box.map50)
    recall = float(metrics.box.r.mean()) if hasattr(metrics.box, "r") else 0.0
    precision = float(metrics.box.p.mean()) if hasattr(metrics.box, "p") else 0.0
    print(f"\nVal mAP@50={map50:.4f}  recall={recall:.4f}  precision={precision:.4f}")

    info = {
        "type": "yolov8n_tiled",
        "model": MODEL,
        "n_classes": 1,
        "tile_size": TILE_SIZE,
        "tile_stride": TILE_STRIDE,
        "resize_max": RESIZE_MAX,
        "imgsz": IMGSZ,
        "eval_score_thresh": 0.25,
        "eval_nms_iou": 0.3,
        "val_map50": round(map50, 4),
        "val_recall": round(recall, 4),
        "val_precision": round(precision, 4),
        "train_tablets": train_tablets,
        "val_tablets": val_tablets,
        "n_train_tiles": n_train,
        "epochs": EPOCHS,
    }
    (ML_DIR / "detector_info.json").write_text(json.dumps(info, indent=2))
    print(f"detector_info.json updated")


if __name__ == "__main__":
    main()
