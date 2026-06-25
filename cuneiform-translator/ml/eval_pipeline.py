"""
End-to-end pipeline evaluation: YOLO detect → EfficientNet classify → compare vs GT labels.

Measures how accurately the full two-stage pipeline recovers the correct sign
sequence from a tablet image, using IoU-matched GT annotations as ground truth.

Usage:
    python ml/eval_pipeline.py [--tablets N]  # N tablets to evaluate (default: all val)

Output: per-tablet recall/precision and sign-level top-1 / top-3 accuracy.
"""

import argparse
import ast
import csv
import datetime
import json
import sys
from pathlib import Path

import torch
from PIL import Image
from torchvision.ops import box_iou

ML_DIR      = Path(__file__).parent
TABLETS_DIR = ML_DIR / "data" / "tablets"
CSV_FILES   = [Path("/tmp/saa05.csv"), Path("/tmp/saa06.csv"), Path("/tmp/saa09.csv")]
INFO_PATH   = ML_DIR / "detector_info.json"

MATCH_IOU = 0.5


def load_annotations():
    annots = {}
    for f in CSV_FILES:
        if not f.exists():
            continue
        for row in csv.DictReader(open(f)):
            pnum = row["tablet_CDLI"]
            annots.setdefault(pnum, []).append({
                "bbox": ast.literal_eval(row["bbox"]),
                "train_label": row["train_label"],
                "mzl_label": row["mzl_label"],
            })
    return annots


def get_val_tablets(annotations):
    if INFO_PATH.exists():
        info = json.loads(INFO_PATH.read_text())
        val = [t for t in info.get("val_tablets", []) if (TABLETS_DIR / f"{t}.jpg").exists()]
        if val:
            return val
    return sorted(t for t in annotations if (TABLETS_DIR / f"{t}.jpg").exists())[:7]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tablets", type=int, default=None, help="Max tablets to evaluate")
    args = parser.parse_args()

    sys.path.insert(0, str(ML_DIR.parent / "backend"))
    sys.path.insert(0, str(ML_DIR))

    # Import recognizer (loads models lazily)
    from recognize import CuneiformRecognizer
    rec = CuneiformRecognizer()
    rec._load_classifier()
    rec._load_detector()

    annotations = load_annotations()
    val_tablets = get_val_tablets(annotations)
    if args.tablets:
        val_tablets = val_tablets[:args.tablets]

    print(f"Evaluating {len(val_tablets)} tablets: {val_tablets}\n")

    label_map = json.loads((ML_DIR / "label_map.json").read_text())
    tl_to_ci  = label_map["train_label_to_class"]  # train_label str → class idx

    total_det_tp = total_det_gt = total_det_pred = 0
    total_clf_top1 = total_clf_top3 = total_clf_total = 0
    per_tablet = []

    for pnum in val_tablets:
        img = Image.open(TABLETS_DIR / f"{pnum}.jpg").convert("RGB")
        gt_entries = annotations[pnum]
        gt_boxes_raw = [e["bbox"] for e in gt_entries]
        gt_labels    = [e["train_label"] for e in gt_entries]

        # Run detector
        pred_boxes = rec._detect_signs(img, score_thresh=0.25)
        n_pred = len(pred_boxes)
        n_gt   = len(gt_boxes_raw)

        if not pred_boxes:
            print(f"  {pnum}: NO DETECTIONS  gt={n_gt}")
            total_det_gt += n_gt
            per_tablet.append({"p_number": pnum, "n_gt": n_gt, "n_pred": 0,
                                "det_recall": 0, "det_precision": 0,
                                "clf_top1": 0, "clf_top3": 0, "clf_total": 0})
            continue

        pred_t = torch.tensor(pred_boxes, dtype=torch.float32)
        gt_t   = torch.tensor(gt_boxes_raw, dtype=torch.float32)
        iou_mat = box_iou(pred_t, gt_t)

        best_gt_iou, best_gt_idx = iou_mat.max(dim=1)
        det_tp = (best_gt_iou >= MATCH_IOU).sum().item()

        # Classify matched detections and check sign labels
        clf_top1 = clf_top3 = clf_total = 0
        for i, (iou_val, gt_idx) in enumerate(zip(best_gt_iou.tolist(), best_gt_idx.tolist())):
            if iou_val < MATCH_IOU:
                continue
            bx1, by1, bx2, by2 = pred_boxes[i]
            crop = img.crop((int(bx1), int(by1), int(bx2), int(by2)))

            # Get top-3 predictions with TTA
            rgb = crop.convert("RGB")
            tta_tfs = getattr(rec, "_tta_transforms", None)
            if tta_tfs:
                avg_probs = None
                for tf in tta_tfs:
                    x = tf(rgb).unsqueeze(0)
                    with torch.no_grad():
                        p = torch.softmax(rec._classifier(x), dim=1)
                    avg_probs = p if avg_probs is None else avg_probs + p
                avg_probs = avg_probs / len(tta_tfs)
                top3_idx = avg_probs[0].topk(3).indices.tolist()
            else:
                x = rec._classifier_transform(rgb).unsqueeze(0)
                with torch.no_grad():
                    logits = rec._classifier(x)
                top3_idx = logits[0].topk(3).indices.tolist()

            gt_tl = gt_labels[gt_idx]
            gt_ci = tl_to_ci.get(gt_tl)
            if gt_ci is None:
                continue

            clf_total += 1
            if top3_idx[0] == gt_ci:
                clf_top1 += 1
                clf_top3 += 1
            elif gt_ci in top3_idx:
                clf_top3 += 1

        det_recall    = det_tp / n_gt  if n_gt   else 0
        det_precision = det_tp / n_pred if n_pred else 0
        clf_acc1 = clf_top1 / clf_total if clf_total else 0
        clf_acc3 = clf_top3 / clf_total if clf_total else 0
        print(
            f"  {pnum}: det_R={det_recall:.2f} det_P={det_precision:.2f}  "
            f"clf_top1={clf_acc1:.2f} clf_top3={clf_acc3:.2f}  "
            f"({clf_top1}/{clf_total} correct)"
        )
        per_tablet.append({
            "p_number": pnum, "n_gt": n_gt, "n_pred": n_pred,
            "det_tp": det_tp, "det_recall": round(det_recall, 4),
            "det_precision": round(det_precision, 4),
            "clf_top1": round(clf_acc1, 4), "clf_top3": round(clf_acc3, 4),
            "clf_correct": clf_top1, "clf_total": clf_total,
        })

        total_det_tp   += det_tp
        total_det_gt   += n_gt
        total_det_pred += n_pred
        total_clf_top1 += clf_top1
        total_clf_top3 += clf_top3
        total_clf_total += clf_total

    print()
    det_R = total_det_tp / total_det_gt   if total_det_gt   else 0
    det_P = total_det_tp / total_det_pred if total_det_pred else 0
    clf1  = total_clf_top1 / total_clf_total if total_clf_total else 0
    clf3  = total_clf_top3 / total_clf_total if total_clf_total else 0
    e2e   = det_R * clf1
    print(f"Overall detector:    recall={det_R:.3f}  precision={det_P:.3f}")
    print(f"Overall classifier:  top-1={clf1:.3f}    top-3={clf3:.3f}")
    print(f"End-to-end top-1:    {e2e:.3f}  (det_recall × clf_top1)")

    # Persist results
    model_info = json.loads((ML_DIR / "model_info.json").read_text()) if (ML_DIR / "model_info.json").exists() else {}
    results = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "classifier_backbone": model_info.get("backbone", "unknown"),
        "classifier_val_acc": model_info.get("best_val_acc"),
        "n_tablets": len(val_tablets),
        "match_iou": MATCH_IOU,
        "overall": {
            "det_recall":    round(det_R, 4),
            "det_precision": round(det_P, 4),
            "clf_top1":      round(clf1, 4),
            "clf_top3":      round(clf3, 4),
            "e2e_top1":      round(e2e, 4),
        },
        "per_tablet": per_tablet,
    }
    out_path = ML_DIR / "eval_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
