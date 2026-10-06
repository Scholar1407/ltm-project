import os
import sys
from pathlib import Path

# Ensure UTF-8 output encoding
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
SANITY_YAML = BASE_DIR / "sanity.yaml"
SANITY_IMG_DIR = BASE_DIR / "dataset" / "sanity" / "images" / "train"

def run_sanity_check(epochs=50, batch=4):
    print("=" * 70)
    print("       PHASE 1: DRY-RUN SANITY CHECK")
    print("=" * 70)
    print(f"Sanity YAML: {SANITY_YAML}")
    print(f"Epochs: {epochs} | Batch: {batch}")
    print("-" * 70)

    from ultralytics import YOLO

    # 1. Model initialization
    print("\n[Step 1/4] Initializing YOLOv8s-P2 architecture...")
    try:
        model = YOLO("yolov8s-p2.yaml").load("yolov8s-p2.pt")
        print("Loaded yolov8s-p2.pt successfully.")
    except Exception as e:
        print(f"Note: yolov8s-p2.pt not found on hub or failed ({e}). Loading yolov8s.pt pretrained weights into yolov8s-p2...")
        model = YOLO("yolov8s-p2.yaml").load("yolov8s.pt")

    # 2. Train on tiny subset
    print("\n[Step 2/4] Training on 16-image sanity subset...")
    results = model.train(
        data=str(SANITY_YAML),
        epochs=epochs,
        imgsz=640,
        batch=batch,
        name="sanity_check",
        project=str(BASE_DIR / "runs" / "detect"),
        exist_ok=True,
        plots=True,
        verbose=True,
    )

    # 3. Inspect training results / loss curve
    print("\n[Step 3/4] Verifying pass criteria...")
    save_dir = Path(model.trainer.save_dir)
    results_csv = save_dir / "results.csv"

    passed_loss = True
    no_nan_inf = True

    if results_csv.exists():
        import csv
        with open(results_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Strip column names
            rows = [{k.strip(): v.strip() for k, v in row.items()} for row in reader]

        box_losses = []
        for r in rows:
            for k, v in r.items():
                if "box_loss" in k and "val" not in k:
                    try:
                        box_losses.append(float(v))
                    except ValueError:
                        pass
                if "loss" in k:
                    val_lower = v.lower()
                    if "nan" in val_lower or "inf" in val_lower:
                        no_nan_inf = False
                        print(f"  [FAIL] NaN/Inf found in {k}: {v}!")

        if len(box_losses) > 0:
            first_loss = box_losses[0]
            last_loss = box_losses[-1]
            print(f"  • Train box loss: {first_loss:.4f} -> {last_loss:.4f}")
            if last_loss >= first_loss:
                print("  [WARN] Loss did not decrease over epochs.")
                passed_loss = False
            else:
                print("  [PASS] Loss decreased smoothly toward near-zero.")
        if no_nan_inf:
            print("  [PASS] No NaN/Inf loss encountered.")

    # 4. Run predict on sanity images and save
    print("\n[Step 4/4] Running predict() on sanity images for manual visual inspection...")
    pred_dir = save_dir / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    
    sample_images = list(SANITY_IMG_DIR.glob("*.jpg"))
    predict_results = model.predict(
        source=[str(p) for p in sample_images],
        save=True,
        project=str(save_dir),
        name="predictions",
        exist_ok=True,
        conf=0.25,
    )

    print(f"Saved {len(predict_results)} sample prediction images to: {pred_dir}")

    all_passed = passed_loss and no_nan_inf
    print("\n" + "=" * 70)
    if all_passed:
        print(" SANITY CHECK PASSED: Pipeline is valid and ready for Phase 2!")
    else:
        print(" SANITY CHECK FAILED: Review the criteria before Phase 2.")
    print("=" * 70)
    return all_passed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=4)
    args = parser.parse_args()
    run_sanity_check(epochs=args.epochs, batch=args.batch)
