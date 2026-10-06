import os
from pathlib import Path

IMG_W = 640
IMG_H = 640

BASE_DIR = Path(__file__).resolve().parent.parent
LABELS_DIR = BASE_DIR / "dataset" / "labels"
SPLITS = ["train", "valid", "test"]

total_boxes = 0
area_less_32x32 = 0
both_less_32 = 0
either_less_32 = 0
width_less_32 = 0
height_less_32 = 0

bin_size = 16
max_bin = 256
num_bins = (max_bin + bin_size - 1) // bin_size
width_bins = [0] * (num_bins + 1)
height_bins = [0] * (num_bins + 1)

area_bins = [
    {"label": "< 16x16 (area < 256)", "max_area": 256, "count": 0},
    {"label": "16x16 - 32x32 (256 <= area < 1024)", "max_area": 1024, "count": 0},
    {"label": "32x32 - 48x48 (1024 <= area < 2304)", "max_area": 2304, "count": 0},
    {"label": "48x48 - 64x64 (2304 <= area < 4096)", "max_area": 4096, "count": 0},
    {"label": "64x64 - 96x96 (4096 <= area < 9216)", "max_area": 9216, "count": 0},
    {"label": "96x96 - 128x128 (9216 <= area < 16384)", "max_area": 16384, "count": 0},
    {"label": ">= 128x128 (area >= 16384)", "max_area": float("inf"), "count": 0},
]

split_stats = {}

for split in SPLITS:
    s_dir = LABELS_DIR / split
    split_stats[split] = {
        "files": 0,
        "empty_files": 0,
        "boxes": 0,
        "area_less_32x32": 0,
        "both_less_32": 0,
        "either_less_32": 0,
    }
    if not s_dir.exists():
        continue

    files = list(s_dir.glob("*.txt"))
    split_stats[split]["files"] = len(files)

    for f in files:
        content = f.read_text(encoding="utf-8").strip()
        if not content:
            split_stats[split]["empty_files"] += 1
            continue

        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5:
                w_norm = float(parts[3])
                h_norm = float(parts[4])

                w_px = w_norm * IMG_W
                h_px = h_norm * IMG_H
                area_px = w_px * h_px

                total_boxes += 1
                split_stats[split]["boxes"] += 1

                is_area_small = area_px < (32 * 32)
                is_both_small = (w_px < 32) and (h_px < 32)
                is_w_small = w_px < 32
                is_h_small = h_px < 32
                is_either_small = (w_px < 32) or (h_px < 32)

                if is_area_small:
                    area_less_32x32 += 1
                    split_stats[split]["area_less_32x32"] += 1
                if is_both_small:
                    both_less_32 += 1
                    split_stats[split]["both_less_32"] += 1
                if is_w_small:
                    width_less_32 += 1
                if is_h_small:
                    height_less_32 += 1
                if is_either_small:
                    either_less_32 += 1
                    split_stats[split]["either_less_32"] += 1

                w_idx = min(int(w_px // bin_size), num_bins)
                width_bins[w_idx] += 1

                h_idx = min(int(h_px // bin_size), num_bins)
                height_bins[h_idx] += 1

                for b in area_bins:
                    if area_px < b["max_area"]:
                        b["count"] += 1
                        break

print("=" * 70)
print("           BOUNDING BOX SIZE & HISTOGRAM ANALYSIS (640x640)")
print("=" * 70)
print(f"Total Bounding Boxes Analyzed: {total_boxes:,}\n")

print("--- 1. CRITERIA FOR BBOX < 32x32 px ---")
print(f"• Standard COCO Small Object (Area < 32x32 = 1024 px²):")
print(f"  Count: {area_less_32x32:,} / {total_boxes:,}")
print(f"  Percentage: {(area_less_32x32 / total_boxes * 100):.2f}%\n")

print(f"• Both Dimensions < 32px (Width < 32px AND Height < 32px):")
print(f"  Count: {both_less_32:,} / {total_boxes:,}")
print(f"  Percentage: {(both_less_32 / total_boxes * 100):.2f}%\n")

print(f"• Either Dimension < 32px (Width < 32px OR Height < 32px):")
print(f"  Count: {either_less_32:,} / {total_boxes:,}")
print(f"  Percentage: {(either_less_32 / total_boxes * 100):.2f}%\n")

print(f"• Width < 32px:  {width_less_32:,} ({(width_less_32 / total_boxes * 100):.2f}%)")
print(f"• Height < 32px: {height_less_32:,} ({(height_less_32 / total_boxes * 100):.2f}%)\n")

print("--- 2. BREAKDOWN BY DATASET SPLIT ---")
for split, stats in split_stats.items():
    b_count = stats["boxes"]
    print(f"[{split.upper()}]")
    print(f"  Total images: {stats['files']:,} ({stats['empty_files']} empty)")
    print(f"  Total bboxes: {b_count:,}")
    if b_count > 0:
        print(f"  Area < 1024 px²: {stats['area_less_32x32']:,} ({(stats['area_less_32x32'] / b_count * 100):.2f}%)")
        print(f"  Both w,h < 32px: {stats['both_less_32']:,} ({(stats['both_less_32'] / b_count * 100):.2f}%)")
        print(f"  Either w,h < 32px: {stats['either_less_32']:,} ({(stats['either_less_32'] / b_count * 100):.2f}%)")

print("\n--- 3. AREA DISTRIBUTION HISTOGRAM ---")
for b in area_bins:
    pct = (b["count"] / total_boxes) * 100
    bar = "█" * round(pct / 2)
    print(f"{b['label']:<35} | {b['count']:>5} ({pct:>5.2f}%) {bar}")

print("\n--- 4. WIDTH DISTRIBUTION (Bin: 16px) ---")
for i in range(num_bins + 1):
    r_str = f">= {max_bin}px" if i == num_bins else f"{i*bin_size}-{(i+1)*bin_size}px"
    count = width_bins[i]
    pct = (count / total_boxes) * 100
    bar = "█" * round(pct / 2)
    print(f"{r_str:<12} | {count:>5} ({pct:>5.2f}%) {bar}")

print("\n--- 5. HEIGHT DISTRIBUTION (Bin: 16px) ---")
for i in range(num_bins + 1):
    r_str = f">= {max_bin}px" if i == num_bins else f"{i*bin_size}-{(i+1)*bin_size}px"
    count = height_bins[i]
    pct = (count / total_boxes) * 100
    bar = "█" * round(pct / 2)
    print(f"{r_str:<12} | {count:>5} ({pct:>5.2f}%) {bar}")
