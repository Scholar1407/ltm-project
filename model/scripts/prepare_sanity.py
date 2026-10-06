import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"
SANITY_DIR = DATASET_DIR / "sanity"

TRAIN_IMG_DIR = DATASET_DIR / "images" / "train"
TRAIN_LBL_DIR = DATASET_DIR / "labels" / "train"

def setup_sanity_subset(num_samples=16):
    """
    Select `num_samples` clean single-subject images with exactly 1 or 2 clear bounding boxes
    to create a tiny sanity dataset for dry-run verification.
    """
    print("Preparing sanity check subset...")
    
    # Destination directories
    img_dest = SANITY_DIR / "images" / "train"
    lbl_dest = SANITY_DIR / "labels" / "train"
    val_img_dest = SANITY_DIR / "images" / "val"
    val_lbl_dest = SANITY_DIR / "labels" / "val"

    for d in [img_dest, lbl_dest, val_img_dest, val_lbl_dest]:
        d.mkdir(parents=True, exist_ok=True)

    # Pick samples
    lbl_files = sorted(list(TRAIN_LBL_DIR.glob("*.txt")))
    selected = []

    for f in lbl_files:
        content = f.read_text(encoding="utf-8").strip()
        lines = [l for l in content.splitlines() if l.strip()]
        # Check if single bounding box with reasonable size (not tiny artifact, not composite)
        if len(lines) == 1:
            parts = lines[0].split()
            w, h = float(parts[3]), float(parts[4])
            if 0.03 < w < 0.5 and 0.03 < h < 0.5:
                img_candidate = TRAIN_IMG_DIR / f"{f.stem}.jpg"
                if img_candidate.exists():
                    selected.append((img_candidate, f))
                    if len(selected) >= num_samples:
                        break

    print(f"Selected {len(selected)} samples for sanity check.")

    for img_path, lbl_path in selected:
        shutil.copy2(img_path, img_dest / img_path.name)
        shutil.copy2(lbl_path, lbl_dest / lbl_path.name)
        # Also copy to val so validation during sanity check works
        shutil.copy2(img_path, val_img_dest / img_path.name)
        shutil.copy2(lbl_path, val_lbl_dest / lbl_path.name)

    # Create sanity.yaml in project root
    yaml_content = f"""path: {SANITY_DIR.as_posix()}
train: images/train
val: images/val

nc: 1
names: ['smoke']
"""
    yaml_path = BASE_DIR / "sanity.yaml"
    yaml_path.write_text(yaml_content, encoding="utf-8")
    print(f"Created sanity.yaml at {yaml_path}")
    print(f"Sanity subset ready with {len(selected)} images.")

if __name__ == "__main__":
    setup_sanity_subset(16)
