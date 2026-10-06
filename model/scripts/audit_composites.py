import os
import sys
from pathlib import Path

# Ensure UTF-8 output encoding for console on Windows
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"
LABELS_DIR = DATASET_DIR / "labels"
IMAGES_DIR = DATASET_DIR / "images"

SPLITS = ["test", "valid", "train"]


def audit_composites(max_clean_boxes=2, save_paths=True):
    """
    Audit dataset for composite/collage images vs single-subject images.
    Heuristic: Images with >= 3 bounding boxes are flagged as multi-panel composites.
    Clean subset: Images with 1 <= bbox_count <= max_clean_boxes.
    """
    print("=" * 70)
    print("      COMPOSITE IMAGE AUDIT & CLEAN SUBSET GENERATION")
    print("=" * 70)
    print(f"Dataset root: {DATASET_DIR}")
    print(f"Heuristic threshold: >= 3 bounding boxes -> Composite/Collage")
    print(f"Clean criteria: 1 to {max_clean_boxes} bounding boxes (single-subject)")
    print("-" * 70)

    summary_stats = {}

    for split in SPLITS:
        lbl_dir = LABELS_DIR / split
        img_dir = IMAGES_DIR / split
        if not lbl_dir.exists():
            continue

        lbl_files = sorted(list(lbl_dir.glob("*.txt")))
        total_images = len(lbl_files)

        box_count_distribution = {}
        clean_ids = []  # Image stem (ID)
        clean_img_paths = []  # Path to image file
        composite_ids = []
        empty_ids = []

        for lbl_file in lbl_files:
            stem = lbl_file.stem
            content = lbl_file.read_text(encoding="utf-8").strip()
            lines = [l for l in content.splitlines() if l.strip()]
            num_boxes = len(lines)

            box_count_distribution[num_boxes] = box_count_distribution.get(num_boxes, 0) + 1

            if num_boxes == 0:
                empty_ids.append(stem)
            elif num_boxes >= 3:
                composite_ids.append(stem)
            else:
                # 1 or 2 boxes -> single-subject
                clean_ids.append(stem)
                # find matching image file
                for ext in [".jpg", ".jpeg", ".png"]:
                    img_path = img_dir / f"{stem}{ext}"
                    if img_path.exists():
                        clean_img_paths.append(f"images/{split}/{img_path.name}")
                        break

        summary_stats[split] = {
            "total": total_images,
            "clean_count": len(clean_ids),
            "composite_count": len(composite_ids),
            "empty_count": len(empty_ids),
            "distribution": box_count_distribution,
        }

        print(f"\n[{split.upper()}] (Total: {total_images:,} images)")
        print(f"  • Single-subject (Clean, 1-2 boxes): {len(clean_ids):>5} ({len(clean_ids)/total_images*100:5.2f}%)")
        print(f"  • Composite / Collage (>= 3 boxes):  {len(composite_ids):>5} ({len(composite_ids)/total_images*100:5.2f}%)")
        print(f"  • Empty / Negative (0 boxes):        {len(empty_ids):>5} ({len(empty_ids)/total_images*100:5.2f}%)")
        print("  • Bbox count distribution:")
        for count in sorted(box_count_distribution.keys()):
            cnt_imgs = box_count_distribution[count]
            pct = cnt_imgs / total_images * 100
            bar = "█" * round(pct / 2)
            print(f"      {count} boxes: {cnt_imgs:>5} images ({pct:5.2f}%) {bar}")

        # Write clean IDs for valid and test as required by spec
        if split in ["test", "valid"]:
            # Output in project root as clean_test_ids.txt / clean_valid_ids.txt
            out_ids_root = BASE_DIR / f"clean_{split}_ids.txt"
            out_ids_root.write_text("\n".join(clean_ids) + "\n", encoding="utf-8")
            print(f"  -> Saved clean IDs: {out_ids_root}")

            # Also in dataset directory
            out_ids_ds = DATASET_DIR / f"clean_{split}_ids.txt"
            out_ids_ds.write_text("\n".join(clean_ids) + "\n", encoding="utf-8")

            # Save clean image paths list for YOLO direct evaluation
            if save_paths:
                out_paths_ds = DATASET_DIR / f"clean_{split}.txt"
                out_paths_ds.write_text("\n".join(clean_img_paths) + "\n", encoding="utf-8")
                print(f"  -> Saved clean image paths: {out_paths_ds}")

    print("\n" + "=" * 70)
    print("Audit Complete.")
    print("=" * 70)


if __name__ == "__main__":
    audit_composites()
