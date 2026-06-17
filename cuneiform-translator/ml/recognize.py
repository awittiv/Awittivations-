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
MODEL_PATH = ML_DIR / "model.pt"
INFO_PATH  = ML_DIR / "model_info.json"
LABEL_MAP  = ML_DIR / "label_map.json"
TL_TO_MZL  = ML_DIR / "train_to_mzl.json"

# Detector paths
DETECTOR_PATH      = ML_DIR / "detector.pt"
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

    # ── Classifier ───────────────────────────────────────────────────────────

    def _load_classifier(self):
        if self._classifier is not None:
            return

        if not MODEL_PATH.exists():
            raise RuntimeError(f"Classifier model not found at {MODEL_PATH}. Run ml/train.py first.")

        info = json.loads(INFO_PATH.read_text())
        n_classes = info["n_classes"]

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

    def classify_patch(self, patch: Image.Image) -> tuple[int, float]:
        self._load_classifier()
        x = self._classifier_transform(patch.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            logits = self._classifier(x)
            probs = torch.softmax(logits, dim=1)
            conf, cls = probs.max(dim=1)
        return cls.item(), conf.item()

    # ── Detector ─────────────────────────────────────────────────────────────

    def _load_detector(self) -> bool:
        """Load Faster R-CNN detector. Returns True if available."""
        if self._detector_loaded:
            return self._detector is not None
        self._detector_loaded = True

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
            return True
        except Exception as e:
            print(f"[recognize] Detector load failed: {e}")
            return False

    def _detect_signs(self, img: Image.Image, score_thresh: float = 0.5) -> list[tuple[int, int, int, int]]:
        """
        Run Faster R-CNN detector. Returns list of (x1, y1, x2, y2) in original image coords.
        """
        import torchvision.transforms.functional as TF

        w, h = img.size
        scale = min(DETECTOR_MAX_SIZE / max(w, h), 1.0)
        if scale < 1.0:
            img_r = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        else:
            img_r = img
            scale = 1.0

        img_t = TF.to_tensor(img_r.convert("RGB"))
        with torch.no_grad():
            outputs = self._detector([img_t])[0]

        boxes_out = []
        for box, score in zip(outputs["boxes"], outputs["scores"]):
            if score.item() < score_thresh:
                continue
            x1, y1, x2, y2 = box.tolist()
            # Scale back to original image coordinates
            boxes_out.append((
                int(x1 / scale), int(y1 / scale),
                int(x2 / scale), int(y2 / scale),
            ))
        return boxes_out

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

        # Classify each detected crop, collect (y_center, x, sign) tuples
        detections = []
        for x1, y1, x2, y2 in boxes:
            pad = max(2, int(min(x2 - x1, y2 - y1) * 0.1))
            cx1 = max(0, x1 - pad)
            cy1 = max(0, y1 - pad)
            cx2 = min(img.width, x2 + pad)
            cy2 = min(img.height, y2 + pad)
            crop = img.crop((cx1, cy1, cx2, cy2))
            cls_idx, _ = self.classify_patch(crop)
            sign = self._netidx_to_sign.get(cls_idx, "x")
            y_center = (y1 + y2) / 2
            detections.append((y_center, x1, sign))

        # Greedy line clustering: sort by y, group within row_unit/2 tolerance
        detections.sort(key=lambda t: t[0])
        line_groups: list[list[tuple[int, str]]] = []
        current_line: list[tuple[int, str]] = []
        current_y = None
        for y_center, x, sign in detections:
            if current_y is None or abs(y_center - current_y) > row_unit * 0.6:
                if current_line:
                    line_groups.append(current_line)
                current_line = [(x, sign)]
                current_y = y_center
            else:
                current_line.append((x, sign))
                current_y = (current_y + y_center) / 2  # running mean
        if current_line:
            line_groups.append(current_line)

        atf_lines = []
        for line_no, signs in enumerate(line_groups, 1):
            signs_sorted = sorted(signs, key=lambda t: t[0])
            atf_lines.append(f"{line_no}. " + " ".join(s for _, s in signs_sorted))

        return {
            "transliteration": "\n".join(atf_lines) if atf_lines else "(no signs detected)",
            "n_patches": len(boxes),
            "n_high_conf": len(boxes),
            "detector": "faster_rcnn",
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
