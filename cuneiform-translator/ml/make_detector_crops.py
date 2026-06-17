"""
Generate classifier training crops using the YOLO detector.

For each annotated tablet, runs tiled YOLO inference and matches each
detection to the nearest ground-truth box (IoU ≥ 0.5). Matched crops
are saved with the GT sign label, so the classifier sees the same kind
of patches it will receive at inference time.

Usage:
    python ml/make_detector_crops.py

Output:
    ml/data/detector_crops/{train_label}/NNNN.jpg
"""

import ast
import csv
from pathlib import Path

import torch
from PIL import Image
from torchvision.ops import box_iou
from ultralytics import YOLO

ML_DIR      = Path(__file__).parent
TABLETS_DIR = ML_DIR / "data" / "tablets"
OUT_DIR     = ML_DIR / "data" / "detector_crops"
CSV_FILES   = [Path("/tmp/saa05.csv"), Path("/tmp/saa06.csv"), Path("/tmp/saa09.csv")]

YOLO_WEIGHTS = ML_DIR / "detector_yolo.pt"
TILE_SIZE    = 512
TILE_STRIDE  = 256
RESIZE_MAX   = 1200
CONF         = 0.25
NMS_IOU      = 0.3
MATCH_IOU    = 0.5   # min IoU to accept a detection as a GT match
CROP_PAD     = 4     # pixels of padding around crop


def load_annotations() -> dict[str, list[dict]]:
    """Returns {pnum: [{bbox, train_label}, ...]}"""
    annots: dict[str, list] = {}
    for csv_path in CSV_FILES:
        if not csv_path.exists():
            continue
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                pnum = row["tablet_CDLI"]
                annots.setdefault(pnum, []).append({
                    "bbox": ast.literal_eval(row["bbox"]),
                    "train_label": row["train_label"],
                })
    return annots


def run_yolo_tiled(model: YOLO, img: Image.Image) -> tuple[list, list]:
    """Tiled YOLO inference; returns (boxes, scores) in scaled image coords."""
    import numpy as np
    from torchvision.ops import nms

    w, h = img.size
    scale = min(RESIZE_MAX / max(w, h), 1.0)
    img_rs = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS) if scale < 1.0 else img
    rw, rh = img_rs.size

    ys = sorted(set(list(range(0, max(1, rh - TILE_SIZE), TILE_STRIDE)) + [max(0, rh - TILE_SIZE)]))
    xs = sorted(set(list(range(0, max(1, rw - TILE_SIZE), TILE_STRIDE)) + [max(0, rw - TILE_SIZE)]))

    all_boxes, all_scores = [], []
    for y0 in ys:
        y1 = min(y0 + TILE_SIZE, rh)
        for x0 in xs:
            x1 = min(x0 + TILE_SIZE, rw)
            patch = img_rs.crop((x0, y0, x1, y1)).convert("RGB")
            results = model.predict(patch, conf=CONF, iou=NMS_IOU, verbose=False)
            for r in results:
                for box in r.boxes:
                    bx1, by1, bx2, by2 = box.xyxy[0].tolist()
                    all_boxes.append([bx1 + x0, by1 + y0, bx2 + x0, by2 + y0])
                    all_scores.append(float(box.conf[0]))

    if not all_boxes:
        return [], []

    boxes_t = torch.tensor(all_boxes, dtype=torch.float32)
    scores_t = torch.tensor(all_scores)
    keep = nms(boxes_t, scores_t, iou_threshold=NMS_IOU)
    boxes_t = boxes_t[keep]

    # Scale back to original image coords
    boxes_orig = (boxes_t / scale).tolist()
    scores_kept = [all_scores[i] for i in keep.tolist()]
    return boxes_orig, scores_kept


def main():
    model = YOLO(str(YOLO_WEIGHTS))
    annotations = load_annotations()
    tablets = sorted(t for t in annotations if (TABLETS_DIR / f"{t}.jpg").exists())

    # Counter per class for sequential filenames
    counters: dict[str, int] = {}

    total_matched = total_unmatched = 0

    for pnum in tablets:
        img = Image.open(TABLETS_DIR / f"{pnum}.jpg").convert("RGB")
        gt_entries = annotations[pnum]

        gt_boxes = torch.tensor(
            [e["bbox"] for e in gt_entries], dtype=torch.float32
        )  # shape (N, 4)

        pred_boxes, _ = run_yolo_tiled(model, img)
        if not pred_boxes:
            print(f"  {pnum}: no detections")
            continue

        pred_t = torch.tensor(pred_boxes, dtype=torch.float32)

        # IoU matrix: (n_pred, n_gt)
        iou_mat = box_iou(pred_t, gt_boxes)
        best_gt_iou, best_gt_idx = iou_mat.max(dim=1)

        n_matched = 0
        for i, (iou_val, gt_idx) in enumerate(zip(best_gt_iou.tolist(), best_gt_idx.tolist())):
            if iou_val < MATCH_IOU:
                total_unmatched += 1
                continue

            label = gt_entries[gt_idx]["train_label"]
            bx1, by1, bx2, by2 = [int(v) for v in pred_boxes[i]]

            # Pad and clamp
            bx1 = max(0, bx1 - CROP_PAD)
            by1 = max(0, by1 - CROP_PAD)
            bx2 = min(img.width,  bx2 + CROP_PAD)
            by2 = min(img.height, by2 + CROP_PAD)

            if bx2 <= bx1 or by2 <= by1:
                continue

            crop = img.crop((bx1, by1, bx2, by2))
            out_dir = OUT_DIR / label
            out_dir.mkdir(parents=True, exist_ok=True)
            idx = counters.get(label, 0)
            crop.save(out_dir / f"{idx:04d}.jpg", quality=92)
            counters[label] = idx + 1
            n_matched += 1

        total_matched += n_matched
        total_unmatched_here = len(pred_boxes) - n_matched
        print(f"  {pnum}: {len(pred_boxes)} preds → {n_matched} matched, {total_unmatched_here} FP")

    n_classes = len(counters)
    print(f"\nDone: {total_matched} crops across {n_classes} classes → {OUT_DIR}")
    print(f"Unmatched (FP) detections: {total_unmatched}")


if __name__ == "__main__":
    main()
