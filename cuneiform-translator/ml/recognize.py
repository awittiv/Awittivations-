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

MODEL_PATH   = Path(__file__).parent / "model.pt"
INFO_PATH    = Path(__file__).parent / "model_info.json"
LABEL_MAP    = Path(__file__).parent / "label_map.json"
TL_TO_MZL   = Path(__file__).parent / "train_to_mzl.json"

# MZL number → sign name (Borger 2004, covering all signs in our training set)
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
    return f"x" if not mzl_id else f"[{mzl_id}]"


class CuneiformRecognizer:
    def __init__(self):
        self._model = None
        self._transform = None
        # Full lookup chain: network output index → sign name
        self._netidx_to_sign: dict[int, str] = {}
        self._netidx_to_mzl: dict[int, int] = {}

    def _load(self):
        if self._model is not None:
            return

        if not MODEL_PATH.exists():
            raise RuntimeError(
                f"Model not found at {MODEL_PATH}. Run ml/train.py first."
            )

        info = json.loads(INFO_PATH.read_text())
        n_classes = info["n_classes"]

        # Rebuild EfficientNet-B0 with same head
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

        crop_size = info.get("crop_size", 64)
        self._transform = transforms.Compose([
            transforms.Resize((crop_size, crop_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                                 [0.229, 0.224, 0.225]),
        ])

        # Build full mapping chain:
        #   network_idx → folder_name (str) → compact_ci (int)
        #   compact_ci  → train_label (str)
        #   train_label → mzl_id (int)
        #   mzl_id      → sign name (str)
        c2i = info["class_to_idx"]          # folder_str → network_idx
        netidx_to_folder = {v: k for k, v in c2i.items()}   # network_idx → folder_str

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
        self._load()
        x = self._transform(patch.convert("RGB")).unsqueeze(0)
        with torch.no_grad():
            logits = self._model(x)
            probs = torch.softmax(logits, dim=1)
            conf, cls = probs.max(dim=1)
        return cls.item(), conf.item()

    def read_tablet(self, img: Image.Image) -> dict:
        """
        Sliding-window sign detection on a full tablet image.
        Returns ATF-style transliteration grouped into approximate lines.
        """
        self._load()
        w, h = img.size

        gray = ImageOps.autocontrast(img.convert("L"))

        # Estimate sign size: Neo-Assyrian tablets ~60-80 signs per column
        est_sign_px = max(40, h // 70)
        step = int(est_sign_px * 0.55)   # ~55% stride = overlapping windows

        patches, positions = [], []
        for y in range(0, h - est_sign_px, step):
            for x in range(0, w - est_sign_px, step):
                patch = gray.crop((x, y, x + est_sign_px, y + est_sign_px))
                arr = np.array(patch, dtype=np.float32)
                # Skip near-blank clay (low variance) — raised threshold
                if arr.std() < 18:
                    continue
                # Skip if gradient energy is too low (smooth background, no sign strokes)
                gx = np.abs(np.diff(arr, axis=1)).mean()
                gy = np.abs(np.diff(arr, axis=0)).mean()
                if gx + gy < 12:
                    continue
                patches.append(patch.convert("RGB"))
                positions.append((x, y))

        if not patches:
            return {"transliteration": "(no signs detected)", "n_patches": 0, "n_high_conf": 0}

        # Batch classify
        batch = torch.stack([self._transform(p) for p in patches])
        with torch.no_grad():
            logits = self._model(batch)
            probs = torch.softmax(logits, dim=1)
            confs, cls_idxs = probs.max(dim=1)

        # Group high-confidence detections into lines, deduplicate nearby positions
        line_height = est_sign_px
        seen: set[tuple[int, int]] = set()
        lines: dict[int, list[tuple[int, str]]] = {}

        for (x, y), cls_idx, conf in zip(positions, cls_idxs.tolist(), confs.tolist()):
            if conf < 0.60:
                continue
            # Deduplicate: snap to grid to avoid double-counting overlapping windows
            gx = round(x / (step * 0.8)) * step
            gy = round(y / (step * 0.8)) * step
            key = (gx // est_sign_px, gy // est_sign_px)
            if key in seen:
                continue
            seen.add(key)
            sign = self._netidx_to_sign.get(cls_idx, "x")
            line = y // line_height
            lines.setdefault(line, []).append((x, sign))

        atf_lines = []
        for line_no, (_, signs) in enumerate(sorted(lines.items()), 1):
            signs_sorted = sorted(signs, key=lambda t: t[0])
            sign_str = " ".join(s for _, s in signs_sorted)
            atf_lines.append(f"{line_no}. {sign_str}")

        transliteration = "\n".join(atf_lines) if atf_lines else "(no signs detected)"
        return {
            "transliteration": transliteration,
            "n_patches": len(patches),
            "n_high_conf": len(seen),
        }


_recognizer: Optional[CuneiformRecognizer] = None


def get_recognizer() -> CuneiformRecognizer:
    global _recognizer
    if _recognizer is None:
        _recognizer = CuneiformRecognizer()
    return _recognizer
