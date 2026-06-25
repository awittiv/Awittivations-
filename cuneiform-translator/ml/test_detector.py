"""
Quick smoke test for the trained Faster R-CNN detector.

Tests on the first validation tablet and prints detection results.
Usage: python ml/test_detector.py
"""

import ast
import csv
import json
from pathlib import Path

import torch
from PIL import Image
import torchvision.transforms.functional as TF
from torchvision.models.detection import (
    fasterrcnn_mobilenet_v3_large_320_fpn,
    FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
)
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.ops import box_iou

ML_DIR = Path(__file__).parent
TABLETS_DIR = ML_DIR / "data" / "tablets"
MAX_SIZE = 800


def load_annotations():
    annots = {}
    for fn in ["saa05.csv", "saa06.csv", "saa09.csv"]:
        p = Path("/tmp") / fn
        if not p.exists():
            continue
        with open(p) as f:
            for row in csv.DictReader(f):
                pnum = row["tablet_CDLI"]
                bbox = ast.literal_eval(row["bbox"])
                annots.setdefault(pnum, []).append(bbox)
    return annots


def main():
    detector_path = ML_DIR / "detector.pt"
    info_path = ML_DIR / "detector_info.json"

    if not detector_path.exists():
        print("detector.pt not found — run ml/train_detector.py first")
        return

    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    val_tablets = info.get("val_tablets", [])
    print(f"Detector info: recall={info.get('val_recall')}, precision={info.get('val_precision')}")
    print(f"Val tablets: {val_tablets}")

    # Load model
    weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
    model = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes=2)
    model.load_state_dict(torch.load(detector_path, map_location="cpu", weights_only=True))
    model.eval()
    print("Model loaded")

    if not val_tablets:
        print("No val tablets recorded")
        return

    annots = load_annotations()
    pnum = val_tablets[0]
    img_path = TABLETS_DIR / f"{pnum}.jpg"
    if not img_path.exists():
        print(f"Image not found: {img_path}")
        return

    print(f"\nTesting on: {pnum}")
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    scale = min(MAX_SIZE / max(w, h), 1.0)
    if scale < 1.0:
        img_r = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    else:
        img_r = img

    img_t = TF.to_tensor(img_r)
    with torch.no_grad():
        outputs = model([img_t])[0]

    gt_boxes = torch.tensor(
        [[x1 * scale, y1 * scale, x2 * scale, y2 * scale]
         for x1, y1, x2, y2 in annots.get(pnum, [])],
        dtype=torch.float32,
    )

    for thresh in [0.3, 0.4, 0.5]:
        keep = outputs["scores"] >= thresh
        pred_boxes = outputs["boxes"][keep]
        n_pred = pred_boxes.shape[0]
        n_gt = gt_boxes.shape[0]

        if n_gt > 0 and n_pred > 0:
            iou_mat = box_iou(pred_boxes, gt_boxes)
            tp = (iou_mat.max(dim=0).values >= 0.5).sum().item()
            recall = tp / n_gt
            precision = tp / n_pred if n_pred else 0
        else:
            recall = precision = 0.0

        print(f"  thresh={thresh:.1f}: pred={n_pred}, gt={n_gt}, "
              f"recall={recall:.2f}, precision={precision:.2f}")

    print("\nTop-10 detections (score desc):")
    scores = outputs["scores"]
    top_idx = scores.argsort(descending=True)[:10]
    for i in top_idx:
        b = outputs["boxes"][i]
        s = scores[i]
        # Scale back to original coords
        x1, y1, x2, y2 = [v.item() / scale for v in b]
        print(f"  score={s:.3f}  box=[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}]  "
              f"size={x2-x1:.0f}x{y2-y1:.0f}px")


if __name__ == "__main__":
    main()
