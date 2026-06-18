"""
Cuneiform sign recognizer — inference module.

Two-stage pipeline:
  1. Faster R-CNN detector (detector.pt) — finds sign bounding boxes
  2. EfficientNet-B0 classifier (model.pt) — identifies sign class per crop
Falls back to sliding-window when detector.pt is absent.
"""

import json
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import numpy as np
from PIL import Image, ImageOps
from torchvision import models, transforms

ML_DIR = Path(__file__).parent

# Classifier paths
MODEL_PATH        = ML_DIR / "model.pt"
MODEL_V2_PATH     = ML_DIR / "model_v2.pt"   # v2 weights kept for ensemble
INFO_PATH         = ML_DIR / "model_info.json"
LABEL_MAP         = ML_DIR / "label_map.json"
TL_TO_MZL         = ML_DIR / "train_to_mzl.json"

# Detector paths
DETECTOR_PATH      = ML_DIR / "detector.pt"
YOLO_DETECTOR_PATH = ML_DIR / "detector_yolo.pt"
DETECTOR_INFO_PATH = ML_DIR / "detector_info.json"

DETECTOR_MAX_SIZE = 800  # must match train_detector.py

# MZL number → sign name (Borger 2004)
MZL_NAMES = {
    1: "AN", 5: "MIN", 9: "AŠ", 10: "U", 11: "3(disz)",
    14: "ÁŠ", 15: "AŠ₂", 16: "IGI@g", 18: "GIŠ", 20: "EZEN",
    23: "PAP", 24: "KA", 71: "GU₄", 85: "TU", 86: "ŠEŠ",
    89: "NE", 90: "BI", 92: "GAN₂", 98: "DIŠ", 99: "BA",
    110: "DIŠ", 111: "HI", 112: "ÉRIN", 113: "LI", 118: "ŠÀ",
    119: "UD", 127: "MA", 132: "ŠU", 136: "TI", 140: "GA₂",
    141: "GA", 142: "EN", 151: "DU", 164: "KUR", 172: "ŠA₃",
    180: "RA", 181: "MU", 184: "NA", 209: "SU", 215: "GU",
    221: "TUG₂", 223: "NU", 230: "LU₂", 248: "ZA", 252: "NI",
    253: "SI", 254: "A", 255: "AB", 258: "DA", 259: "GI",
    260: "RI", 262: "AK", 266: "AG", 292: "PAD", 298: "ŠU₂",
    302: "IM", 348: "TAK₄", 350: "SAG", 353: "KI", 358: "ZU",
    380: "TA", 437: "DINGIR", 464: "ŠEŠ", 469: "SAR", 485: "DUB",
    486: "GAL", 490: "HAL", 491: "TUM", 494: "ŠID", 495: "NINDA",
    496: "GUR", 498: "NINDA₂", 504: "TUK", 511: "IGI", 514: "PA",
    541: "E₂", 548: "ŠÁ", 552: "NAM", 553: "NUN", 558: "AD",
    559: "UŠ", 560: "KAB", 561: "GÁ×MAŠ", 566: "AL", 567: "DIŠ@t",
    576: "ŠÀ", 578: "LUGAL", 579: "ZAG", 580: "AŠ₂", 589: "IGI",
    592: "AMAR", 596: "GU₇", 598: "KU₃", 599: "UDU", 631: "SILA₃",
    635: "GAN", 636: "GÁ", 641: "IŠ", 644: "UR", 646: "KA×UD",
    661: "NAG", 663: "KU", 708: "GU₂", 711: "NIG₂", 724: "ŠE",
    726: "GIR₂", 731: "IR", 736: "ZI", 737: "MAŠ", 745: "GIR₃",
    747: "TI₈", 748: "ZU", 753: "ŠID", 754: "NIN", 808: "EŠ₂",
    812: "KAŠ", 815: "HAR", 825: "GI₄", 828: "AN", 834: "UGU",
    836: "KAK", 839: "AN", 851: "GIG", 856: "GÍR", 859: "ŠU₂",
    861: "PIRIG", 869: "MUŠ", 883: "UD", 884: "ŠÚ",
}


def _get_sign_name(mzl_id: Optional[int]) -> str:
    if mzl_id and mzl_id in MZL_NAMES:
        return MZL_NAMES[mzl_id]
    return "x" if not mzl_id else f"[{mzl_id}]"


class CuneiformRecognizer:
    def __init__(self):
        self._classifier = None
        self._classifier_transform = None
        self._netidx_to_sign: dict[int, str] = {}
        self._netidx_to_mzl: dict[int, int] = {}
        self._detector = None
        self._detector_loaded = False
        self._detector_type = "faster_rcnn"  # or "yolo"
        self._ensemble_model = None  # secondary model for ensembling

    # ── Classifier ───────────────────────────────────────────────────────────

    def _load_classifier(self):
        if self._classifier is not None:
            return

        if not MODEL_PATH.exists():
            raise RuntimeError(f"Classifier model not found at {MODEL_PATH}. Run ml/train.py first.")

        info = json.loads(INFO_PATH.read_text())
        n_classes = info["n_classes"]
        backbone  = info.get("backbone", "efficientnet_b0")

        if backbone == "efficientnet_b2":
            clf = models.efficientnet_b2(weights=None)
        else:
            clf = models.efficientnet_b0(weights=None)
        in_features = clf.classifier[1].in_features
        clf.classifier = nn.Sequential(
            nn.Dropout(p=0.3, inplace=True),
            nn.Linear(in_features, n_classes),
        )
        clf.load_state_dict(torch.load(MODEL_PATH, map_location="cpu", weights_only=True))
        clf.eval()
        self._classifier = clf

        crop_size = info.get("crop_size", 64)
        self._classifier_transform = transforms.Compose([
            transforms.Resize((crop_size, crop_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        # TTA transforms: flip + brightness variants averaged at inference
        self._tta_transforms = [
            transforms.Compose([
                transforms.Resize((crop_size, crop_size)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]),
            transforms.Compose([
                transforms.Resize((crop_size, crop_size)),
                transforms.RandomHorizontalFlip(p=1.0),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]),
            transforms.Compose([
                transforms.Resize((crop_size + 8, crop_size + 8)),
                transforms.CenterCrop(crop_size),
                transforms.ColorJitter(brightness=0.3),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]),
            transforms.Compose([
                transforms.Resize((crop_size + 8, crop_size + 8)),
                transforms.CenterCrop(crop_size),
                transforms.RandomHorizontalFlip(p=1.0),
                transforms.ColorJitter(brightness=0.3),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]),
        ]

        # Build network_idx → sign name mapping (accounts for lexicographic sort)
        c2i = info["class_to_idx"]  # folder_str → network_idx
        netidx_to_folder = {v: k for k, v in c2i.items()}

        ci_to_tl: dict[int, str] = {}
        if LABEL_MAP.exists():
            lm = json.loads(LABEL_MAP.read_text())
            ci_to_tl = {v: k for k, v in lm["train_label_to_class"].items()}

        tl_to_mzl: dict[str, int] = {}
        if TL_TO_MZL.exists():
            raw = json.loads(TL_TO_MZL.read_text())
            tl_to_mzl = {k: int(v) for k, v in raw.items()}

        for netidx in range(n_classes):
            folder = netidx_to_folder.get(netidx)
            if folder is None:
                continue
            ci = int(folder)
            tl = ci_to_tl.get(ci)
            if tl is None:
                continue
            mzl = tl_to_mzl.get(str(tl))
            if mzl is None:
                continue
            self._netidx_to_mzl[netidx] = mzl
            self._netidx_to_sign[netidx] = _get_sign_name(mzl)

        # Load ensemble model (v2 B0 weights) if v3 B2 is primary
        if MODEL_V2_PATH.exists() and backbone == "efficientnet_b2":
            try:
                ens = models.efficientnet_b0(weights=None)
                ens_in = ens.classifier[1].in_features
                ens.classifier = nn.Sequential(
                    nn.Dropout(p=0.3, inplace=True),
                    nn.Linear(ens_in, n_classes),
                )
                ens.load_state_dict(torch.load(MODEL_V2_PATH, map_location="cpu", weights_only=True))
                ens.eval()
                self._ensemble_model = ens
                print("[recognize] Ensemble model (B0 v2) loaded")
            except Exception as e:
                print(f"[recognize] Ensemble load failed: {e}")

    def classify_patch(self, patch: Image.Image) -> tuple[int, float]:
        self._load_classifier()
        rgb = patch.convert("RGB")
        tta_tfs = getattr(self, "_tta_transforms", None)

        with torch.no_grad():
            if tta_tfs:
                avg_probs = None
                for tf in tta_tfs:
                    x = tf(rgb).unsqueeze(0)
                    p = torch.softmax(self._classifier(x), dim=1)
                    avg_probs = p if avg_probs is None else avg_probs + p
                avg_probs = avg_probs / len(tta_tfs)
            else:
                x = self._classifier_transform(rgb).unsqueeze(0)
                avg_probs = torch.softmax(self._classifier(x), dim=1)

            # Ensemble: average with secondary model if loaded
            if self._ensemble_model is not None:
                x_ens = self._classifier_transform(rgb).unsqueeze(0)
                ens_probs = torch.softmax(self._ensemble_model(x_ens), dim=1)
                avg_probs = 0.6 * avg_probs + 0.4 * ens_probs  # weight B2 higher

        conf, cls = avg_probs.max(dim=1)
        return cls.item(), conf.item()

    # ── Detector ─────────────────────────────────────────────────────────────

    def _load_detector(self) -> bool:
        """Load detector (YOLO preferred, falls back to Faster R-CNN). Returns True if available."""
        if self._detector_loaded:
            return self._detector is not None
        self._detector_loaded = True

        # Prefer YOLO if weights exist
        if YOLO_DETECTOR_PATH.exists():
            try:
                from ultralytics import YOLO
                self._detector = YOLO(str(YOLO_DETECTOR_PATH))
                self._detector_type = "yolo"
                print("[recognize] YOLO detector loaded")
                return True
            except Exception as e:
                print(f"[recognize] YOLO load failed: {e}")

        if not DETECTOR_PATH.exists():
            return False

        try:
            from torchvision.models.detection import (
                fasterrcnn_mobilenet_v3_large_320_fpn,
                FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
            )
            from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

            model = fasterrcnn_mobilenet_v3_large_320_fpn(
                weights=FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
            )
            in_features = model.roi_heads.box_predictor.cls_score.in_features
            model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes=2)
            model.load_state_dict(
                torch.load(DETECTOR_PATH, map_location="cpu", weights_only=True)
            )
            model.eval()
            self._detector = model
            self._detector_type = "faster_rcnn"
            return True
        except Exception as e:
            print(f"[recognize] Detector load failed: {e}")
            return False

    def _detect_signs(self, img: Image.Image, score_thresh: float = 0.2) -> list[tuple[int, int, int, int]]:
        """
        Run detector. Returns list of (x1, y1, x2, y2) in original image coords.
        Uses YOLO when detector_yolo.pt is present, otherwise Faster R-CNN.
        """
        if self._detector_type == "yolo":
            return self._detect_signs_yolo(img, score_thresh)
        return self._detect_signs_frcnn(img, score_thresh)

    def _detect_signs_yolo(self, img: Image.Image, score_thresh: float = 0.25) -> list[tuple[int, int, int, int]]:
        """Tiled YOLO inference."""
        import numpy as np
        from torchvision.ops import nms as tv_nms

        dinfo = {}
        if DETECTOR_INFO_PATH.exists():
            dinfo = json.loads(DETECTOR_INFO_PATH.read_text())
        tile_size = dinfo.get("tile_size", 512)
        tile_stride = dinfo.get("tile_stride", 256)
        resize_max = dinfo.get("resize_max", 1200)
        conf = dinfo.get("eval_score_thresh", score_thresh)
        nms_iou = dinfo.get("eval_nms_iou", 0.3)

        w, h = img.size
        scale = min(resize_max / max(w, h), 1.0)
        img_rs = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS) if scale < 1.0 else img
        rw, rh = img_rs.size

        ys = sorted(set(list(range(0, max(1, rh - tile_size), tile_stride)) + [max(0, rh - tile_size)]))
        xs = sorted(set(list(range(0, max(1, rw - tile_size), tile_stride)) + [max(0, rw - tile_size)]))

        all_boxes: list[list[float]] = []
        all_scores: list[float] = []

        for y0 in ys:
            y1e = min(y0 + tile_size, rh)
            for x0 in xs:
                x1e = min(x0 + tile_size, rw)
                patch = img_rs.crop((x0, y0, x1e, y1e)).convert("RGB")
                results = self._detector.predict(
                    np.array(patch), conf=conf, iou=nms_iou, verbose=False
                )
                for r in results:
                    for box in r.boxes:
                        bx1, by1, bx2, by2 = box.xyxy[0].tolist()
                        all_boxes.append([bx1 + x0, by1 + y0, bx2 + x0, by2 + y0])
                        all_scores.append(float(box.conf[0]))

        if not all_boxes:
            return []

        import torch
        boxes_t = torch.tensor(all_boxes, dtype=torch.float32)
        scores_t = torch.tensor(all_scores)
        keep = tv_nms(boxes_t, scores_t, iou_threshold=nms_iou)
        boxes_t = boxes_t[keep]

        return [
            (int(b[0] / scale), int(b[1] / scale), int(b[2] / scale), int(b[3] / scale))
            for b in boxes_t.tolist()
        ]

    def _detect_signs_frcnn(self, img: Image.Image, score_thresh: float = 0.2) -> list[tuple[int, int, int, int]]:
        """Tiled Faster R-CNN inference."""
        import torchvision.transforms.functional as TF
        from torchvision.ops import nms

        tile_size = None
        tile_stride = None
        resize_max = DETECTOR_MAX_SIZE
        if DETECTOR_INFO_PATH.exists():
            dinfo = json.loads(DETECTOR_INFO_PATH.read_text())
            if dinfo.get("type", "").endswith("_tiled"):
                tile_size = dinfo.get("tile_size", 512)
                tile_stride = dinfo.get("tile_stride", 256)
                resize_max = dinfo.get("resize_max", 1200)

        w, h = img.size
        scale = min(resize_max / max(w, h), 1.0)
        img_rs = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS) if scale < 1.0 else img
        rw, rh = img_rs.size

        all_boxes: list[list[float]] = []
        all_scores: list[float] = []

        if tile_size:
            stride = tile_stride or tile_size // 2
            ys = sorted(set(list(range(0, max(1, rh - tile_size), stride)) + [max(0, rh - tile_size)]))
            xs = sorted(set(list(range(0, max(1, rw - tile_size), stride)) + [max(0, rw - tile_size)]))
            for y0 in ys:
                y1e = min(y0 + tile_size, rh)
                for x0 in xs:
                    x1e = min(x0 + tile_size, rw)
                    patch = img_rs.crop((x0, y0, x1e, y1e))
                    img_t = TF.to_tensor(patch.convert("RGB"))
                    with torch.no_grad():
                        out = self._detector([img_t])[0]
                    for box, sc in zip(out["boxes"], out["scores"]):
                        if sc.item() >= score_thresh:
                            bx1, by1, bx2, by2 = box.tolist()
                            all_boxes.append([bx1 + x0, by1 + y0, bx2 + x0, by2 + y0])
                            all_scores.append(sc.item())
            if not all_boxes:
                return []
            boxes_t = torch.tensor(all_boxes, dtype=torch.float32)
            scores_t = torch.tensor(all_scores)
            keep = nms(boxes_t, scores_t, iou_threshold=0.3)
            boxes_t = boxes_t[keep]
        else:
            img_t = TF.to_tensor(img_rs.convert("RGB"))
            with torch.no_grad():
                out = self._detector([img_t])[0]
            for box, sc in zip(out["boxes"], out["scores"]):
                if sc.item() >= score_thresh:
                    all_boxes.append(box.tolist())
                    all_scores.append(sc.item())
            if not all_boxes:
                return []
            boxes_t = torch.tensor(all_boxes, dtype=torch.float32)

        return [
            (int(b[0] / scale), int(b[1] / scale), int(b[2] / scale), int(b[3] / scale))
            for b in boxes_t.tolist()
        ]

    # ── Main entry point ─────────────────────────────────────────────────────

    def read_tablet(self, img: Image.Image) -> dict:
        """
        Full pipeline: detect sign regions, classify each, return transliteration.
        Uses Faster R-CNN detector when available, falls back to sliding window.
        """
        self._load_classifier()
        has_detector = self._load_detector()

        if has_detector:
            return self._read_with_detector(img)
        else:
            return self._read_sliding_window(img)

    def _read_with_detector(self, img: Image.Image) -> dict:
        """Faster R-CNN detection + EfficientNet classification."""
        boxes = self._detect_signs(img, score_thresh=0.2)

        if not boxes:
            return {
                "transliteration": "(no signs detected)",
                "n_patches": 0,
                "n_high_conf": 0,
                "detector": "faster_rcnn",
            }

        # Estimate median sign height for line grouping
        heights = [y2 - y1 for x1, y1, x2, y2 in boxes]
        heights.sort()
        median_h = heights[len(heights) // 2]
        row_unit = max(median_h, 15)

        CLF_CONF_THRESHOLD = 0.35  # below this → mark sign as uncertain

        # Classify each detected crop, collect (y_center, x1, sign, box, conf) tuples
        detections = []
        for x1, y1, x2, y2 in boxes:
            pad = max(2, int(min(x2 - x1, y2 - y1) * 0.1))
            cx1 = max(0, x1 - pad)
            cy1 = max(0, y1 - pad)
            cx2 = min(img.width, x2 + pad)
            cy2 = min(img.height, y2 + pad)
            crop = img.crop((cx1, cy1, cx2, cy2))
            cls_idx, clf_conf = self.classify_patch(crop)
            base_sign = self._netidx_to_sign.get(cls_idx, "x")
            # Append ? to uncertain readings so Claude and users know not to trust them
            sign = base_sign if clf_conf >= CLF_CONF_THRESHOLD else f"{base_sign}?"
            y_center = (y1 + y2) / 2
            detections.append((y_center, x1, sign, x1, y1, x2, y2, clf_conf))

        # Greedy line clustering by y-center
        detections.sort(key=lambda t: t[0])
        line_groups: list[list[tuple]] = []
        current_line: list[tuple] = []
        current_y = None
        for det in detections:
            y_center = det[0]
            if current_y is None or abs(y_center - current_y) > row_unit * 0.6:
                if current_line:
                    line_groups.append(current_line)
                current_line = [det]
                current_y = y_center
            else:
                current_line.append(det)
                current_y = (current_y + y_center) / 2
        if current_line:
            line_groups.append(current_line)

        atf_lines = []
        det_out = []
        all_confs = []
        for line_no, signs in enumerate(line_groups, 1):
            signs_sorted = sorted(signs, key=lambda t: t[1])  # sort by x1
            atf_lines.append(f"{line_no}. " + " ".join(t[2] for t in signs_sorted))
            for t in signs_sorted:
                _, _, sign, bx1, by1, bx2, by2, clf_conf = t
                det_out.append({
                    "x1": bx1, "y1": by1, "x2": bx2, "y2": by2,
                    "sign": sign, "conf": round(clf_conf, 3),
                })
                all_confs.append(clf_conf)

        n_high_conf = sum(1 for c in all_confs if c >= CLF_CONF_THRESHOLD)
        avg_conf = round(sum(all_confs) / len(all_confs), 3) if all_confs else 0.0

        return {
            "transliteration": "\n".join(atf_lines) if atf_lines else "(no signs detected)",
            "n_patches": len(boxes),
            "n_high_conf": n_high_conf,
            "avg_clf_conf": avg_conf,
            "detector": self._detector_type,
            "detections": det_out,
        }

    def _read_sliding_window(self, img: Image.Image) -> dict:
        """Fallback sliding-window detector (low precision)."""
        w, h = img.size
        gray = ImageOps.autocontrast(img.convert("L"))

        est_sign_px = max(40, h // 70)
        step = int(est_sign_px * 0.55)

        patches, positions = [], []
        for y in range(0, h - est_sign_px, step):
            for x in range(0, w - est_sign_px, step):
                patch = gray.crop((x, y, x + est_sign_px, y + est_sign_px))
                arr = np.array(patch, dtype=np.float32)
                if arr.std() < 18:
                    continue
                gx = np.abs(np.diff(arr, axis=1)).mean()
                gy = np.abs(np.diff(arr, axis=0)).mean()
                if gx + gy < 12:
                    continue
                patches.append(patch.convert("RGB"))
                positions.append((x, y))

        if not patches:
            return {
                "transliteration": "(no signs detected)",
                "n_patches": 0,
                "n_high_conf": 0,
                "detector": "sliding_window",
            }

        batch = torch.stack([self._classifier_transform(p) for p in patches])
        with torch.no_grad():
            logits = self._classifier(batch)
            probs = torch.softmax(logits, dim=1)
            confs, cls_idxs = probs.max(dim=1)

        line_height = est_sign_px
        seen: set = set()
        lines: dict[int, list] = {}

        for (x, y), cls_idx, conf in zip(positions, cls_idxs.tolist(), confs.tolist()):
            if conf < 0.60:
                continue
            gx_snap = round(x / (step * 0.8)) * step
            gy_snap = round(y / (step * 0.8)) * step
            key = (gx_snap // est_sign_px, gy_snap // est_sign_px)
            if key in seen:
                continue
            seen.add(key)
            sign = self._netidx_to_sign.get(cls_idx, "x")
            line_no = y // line_height
            lines.setdefault(line_no, []).append((x, sign))

        atf_lines = []
        for line_no, (_, signs) in enumerate(sorted(lines.items()), 1):
            signs_sorted = sorted(signs, key=lambda t: t[0])
            atf_lines.append(f"{line_no}. " + " ".join(s for _, s in signs_sorted))

        return {
            "transliteration": "\n".join(atf_lines) if atf_lines else "(no signs detected)",
            "n_patches": len(patches),
            "n_high_conf": len(seen),
            "detector": "sliding_window",
        }


_recognizer: Optional[CuneiformRecognizer] = None


def get_recognizer() -> CuneiformRecognizer:
    global _recognizer
    if _recognizer is None:
        _recognizer = CuneiformRecognizer()
    return _recognizer
