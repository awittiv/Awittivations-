"""
Download CDLI tablet photos and crop individual cuneiform sign patches
using the CompVis bounding box annotations.

Outputs: ml/data/crops/<class_id>/<patch_id>.jpg
"""

import csv
import ast
import time
import urllib.request
import urllib.error
from pathlib import Path
from PIL import Image, ImageOps

ANNOTATIONS = [
    "https://raw.githubusercontent.com/CompVis/cuneiform-sign-detection-dataset/master/annotations/bbox_annotations_saa05.csv",
    "https://raw.githubusercontent.com/CompVis/cuneiform-sign-detection-dataset/master/annotations/bbox_annotations_saa06.csv",
    "https://raw.githubusercontent.com/CompVis/cuneiform-sign-detection-dataset/master/annotations/bbox_annotations_saa09.csv",
]

CDLI_PHOTO  = "https://cdli.earth/dl/photo/{p}.jpg"
TABLET_DIR  = Path(__file__).parent / "data" / "tablets"
CROPS_DIR   = Path(__file__).parent / "data" / "crops"
CROP_SIZE   = 64          # px — sign patch output size
MIN_EXAMPLES = 5          # drop classes with fewer examples
HEADERS     = {"User-Agent": "CuneiformTranslator-ML/1.0 (research)"}


def fetch(url: str, dest: Path) -> bool:
    if dest.exists():
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            dest.write_bytes(r.read())
        time.sleep(0.3)  # be polite to CDLI
        return True
    except Exception as e:
        print(f"  SKIP {dest.name}: {e}")
        return False


def load_annotations() -> list[dict]:
    rows = []
    for url in ANNOTATIONS:
        print(f"Fetching {url.split('/')[-1]}...")
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode()
        rows.extend(list(csv.DictReader(text.splitlines())))
    return rows


def filter_classes(rows: list[dict], min_ex: int) -> tuple[list[dict], dict]:
    from collections import Counter
    counts = Counter(r["train_label"] for r in rows)
    keep = {label for label, n in counts.items() if n >= min_ex}
    filtered = [r for r in rows if r["train_label"] in keep]

    # Remap train_label → compact 0-based index
    sorted_labels = sorted(keep, key=lambda x: int(x))
    label_map = {old: new for new, old in enumerate(sorted_labels)}
    return filtered, label_map


def crop_and_save(row: dict, img: Image.Image, label_map: dict, counters: dict):
    bbox = ast.literal_eval(row["bbox"])          # [x1, y1, x2, y2]
    x1, y1, x2, y2 = bbox
    w, h = img.size

    # Clamp to image bounds
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return

    # Add 20% padding around the sign
    pw = int((x2 - x1) * 0.2)
    ph = int((y2 - y1) * 0.2)
    x1, y1 = max(0, x1 - pw), max(0, y1 - ph)
    x2, y2 = min(w, x2 + pw), min(h, y2 + ph)

    patch = img.crop((x1, y1, x2, y2)).convert("L")  # grayscale
    patch = ImageOps.autocontrast(patch)
    patch = patch.resize((CROP_SIZE, CROP_SIZE), Image.LANCZOS)
    patch = patch.convert("RGB")

    train_label = row["train_label"]
    class_idx = label_map[train_label]
    class_dir = CROPS_DIR / str(class_idx)
    class_dir.mkdir(parents=True, exist_ok=True)

    n = counters.get(class_idx, 0)
    patch.save(class_dir / f"{n:04d}.jpg", quality=90)
    counters[class_idx] = n + 1


def main():
    TABLET_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Loading annotations ===")
    rows = load_annotations()
    print(f"Total annotations: {len(rows)}")

    rows, label_map = filter_classes(rows, MIN_EXAMPLES)
    print(f"After filtering (<{MIN_EXAMPLES} examples removed): {len(rows)} annotations, {len(label_map)} classes")

    # Save label map
    import json
    (Path(__file__).parent / "label_map.json").write_text(
        json.dumps({"train_label_to_class": label_map,
                    "n_classes": len(label_map)}, indent=2)
    )

    # Group by tablet
    by_tablet: dict[str, list] = {}
    for r in rows:
        by_tablet.setdefault(r["tablet_CDLI"], []).append(r)

    print(f"\n=== Downloading {len(by_tablet)} tablet photos ===")
    counters: dict[int, int] = {}
    for i, (p_number, tablet_rows) in enumerate(sorted(by_tablet.items()), 1):
        img_path = TABLET_DIR / f"{p_number}.jpg"
        print(f"[{i:2d}/{len(by_tablet)}] {p_number}  ({len(tablet_rows)} signs)...", end=" ")
        ok = fetch(CDLI_PHOTO.format(p=p_number), img_path)
        if not ok:
            continue
        try:
            img = Image.open(img_path)
        except Exception as e:
            print(f"bad image: {e}")
            continue

        for row in tablet_rows:
            crop_and_save(row, img, label_map, counters)
        print("ok")

    total_crops = sum(counters.values())
    print(f"\n=== Done: {total_crops} sign crops across {len(counters)} classes ===")
    print(f"Crops saved to: {CROPS_DIR}")


if __name__ == "__main__":
    main()
