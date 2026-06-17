"""
Cuneiform sign recognizer — inference module.

Given a tablet image, uses a sliding-window approach to detect sign regions,
classifies each with the trained EfficientNet-B0, and returns a structured
list of sign labels that can be passed to Claude for translation.
"""

import json
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import numpy as np
from PIL import Image, ImageOps
from torchvision import models, transforms

MODEL_PATH = Path(__file__).parent / "model.pt"
INFO_PATH  = Path(__file__).parent / "model_info.json"
LABEL_MAP  = Path(__file__).parent / "label_map.json"

# MZL number → sign name (most common Neo-Assyrian signs)
# Subset of the ~900-sign MZL list (Borger 2004)
MZL_NAMES = {
    1: "AN", 2: "AŠ", 4: "DIŠ", 5: "MIN", 6: "EŠ",
    13: "U", 14: "ÁŠ", 15: "AŠ₂", 18: "GIŠ", 21: "TUG₂",
    24: "KA", 26: "ŠA", 28: "SAG", 36: "UD", 46: "KI",
    55: "DU", 56: "ŠU", 57: "KUR", 58: "LU₂", 61: "IM",
    62: "UG", 68: "NI", 72: "TI", 73: "RI", 74: "GI",
    79: "AB", 80: "ZA", 99: "BA", 110: "DIŠ", 112: "ÉRIN",
    113: "LI", 116: "AK", 122: "GAL", 131: "DUB", 142: "EN",
    155: "TUM", 167: "LUGAL", 184: "NA", 231: "MU",
    298: "ŠU₂", 313: "A", 354: "I", 381: "U₂",
    383: "NU", 396: "PA", 399: "E₂", 411: "NAM",
    449: "ŠÀ", 554: "BI", 589: "IGI", 597: "DINGIR",
    651: "QA", 748: "ZU", 757: "NIN", 759: "INANNA",
    839: "AN",
}


def _get_sign_name(mzl_id: Optional[int]) -> str:
    if mzl_id and mzl_id in MZL_NAMES:
        return MZL_NAMES[mzl_id]
    return f"sign{mzl_id}" if mzl_id else "?"


class CuneiformRecognizer:
    def __init__(self):
        self._model = None
        self._info = None
        self._transform = None
        self._label_map_inv = None  # class_idx → mzl_label

    def _load(self):
        if self._model is not None:
            return

        if not MODEL_PATH.exists():
            raise RuntimeError(
                f"Model not found at {MODEL_PATH}. Run ml/train.py first."
            )

        info = json.loads(INFO_PATH.read_text())
        self._info = info
        n_classes = info["n_classes"]

        # Rebuild model
        model = models.efficientnet_b0(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(
            nn.Dropout(p=0.3, inplace=True),
            nn.Linear(in_features, n_classes),
        )
        model.load_state_dict(
            torch.load(MODEL_PATH, map_location="cpu", weights_only=True)
        )
        model.eval()
        self._model = model

        # Transform for inference
        crop_size = info.get("crop_size", 64)
        self._transform = transforms.Compose([
            transforms.Resize((crop_size, crop_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225]),
        ])

        # Build inverse label map: class_idx (folder name int) → compact class index
        # class_to_idx maps folder name → network output index
        self._class_to_idx = info["class_to_idx"]  # folder_name_str → network_idx
        # Also load original label_map to get mzl labels per class
        if LABEL_MAP.exists():
            lm = json.loads(LABEL_MAP.read_text())
            # train_label → compact class index
            tl_to_ci = lm["train_label_to_class"]
            # invert: compact_class_index → train_label
            self._ci_to_tl = {v: k for k, v in tl_to_ci.items()}
        else:
            self._ci_to_tl = {}

    def classify_patch(self, patch: Image.Image) -> tuple[int, float]:
        """Return (class_index, confidence) for a single sign patch."""
        self._load()
        x = self._transform(patch.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            logits = self._model(x)
            probs = torch.softmax(logits, dim=1)
            conf, cls = probs.max(dim=1)
        return cls.item(), conf.item()

    def recognize_patches(self, patches: list[Image.Image]) -> list[dict]:
        """Classify a list of sign patches. Returns list of {sign, confidence}."""
        self._load()
        results = []
        for patch in patches:
            cls_idx, conf = self.classify_patch(patch)
            # Map network output index back to train_label
            # The ImageFolder sorts folder names lexicographically
            # folders are named by compact class index (0, 1, 2, ...)
            train_label = self._ci_to_tl.get(cls_idx)
            mzl_id = int(train_label) if train_label else None
            results.append({
                "class_idx": cls_idx,
                "train_label": train_label,
                "sign": _get_sign_name(mzl_id),
                "confidence": round(conf, 3),
            })
        return results

    def read_tablet(self, img: Image.Image, stride_ratio: float = 0.6) -> dict:
        """
        Sliding-window sign detection on a full tablet image.

        Returns estimated sign sequence and a rough ATF-style transliteration.
        Note: this is a prototype — proper line segmentation needs more work.
        """
        self._load()
        w, h = img.size

        # Convert to grayscale, enhance contrast
        gray = ImageOps.autocontrast(img.convert("L"))

        # Estimate sign size from image dimensions
        # Neo-Assyrian tablets ~60-80 signs per column, tablet ~4000px tall
        est_sign_px = max(40, h // 70)
        step = int(est_sign_px * stride_ratio)

        patches = []
        positions = []
        for y in range(0, h - est_sign_px, step):
            for x in range(0, w - est_sign_px, step):
                patch = gray.crop((x, y, x + est_sign_px, y + est_sign_px))
                # Skip mostly blank patches (background clay)
                arr = np.array(patch)
                if arr.std() < 8:
                    continue
                patches.append(patch.convert("RGB"))
                positions.append((x, y))

        if not patches:
            return {"signs": [], "transliteration": "(no signs detected)"}

        results = self.recognize_patches(patches)

        # Group into approximate lines (by y position)
        line_height = est_sign_px
        lines: dict[int, list] = {}
        for (x, y), r in zip(positions, results):
            if r["confidence"] < 0.4:
                continue
            line = y // line_height
            lines.setdefault(line, []).append((x, r))

        # Build ATF-style output
        atf_lines = []
        for line_no, (line_y, signs) in enumerate(sorted(lines.items()), 1):
            signs_sorted = sorted(signs, key=lambda t: t[0])
            sign_str = " ".join(s["sign"] for _, s in signs_sorted)
            atf_lines.append(f"{line_no}. {sign_str}")

        transliteration = "\n".join(atf_lines) if atf_lines else "(no signs detected)"

        return {
            "signs": results,
            "transliteration": transliteration,
            "n_patches": len(patches),
            "n_high_conf": sum(1 for r in results if r["confidence"] >= 0.4),
        }


# Singleton for the backend
_recognizer: Optional[CuneiformRecognizer] = None


def get_recognizer() -> CuneiformRecognizer:
    global _recognizer
    if _recognizer is None:
        _recognizer = CuneiformRecognizer()
    return _recognizer
