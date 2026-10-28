import os
import sys
from pathlib import Path
from ultralytics import YOLO

# Ensure UTF-8 output encoding
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent  # model/
PROJECT_ROOT = BASE_DIR.parent
DATASET_DIR = BASE_DIR / "dataset"

P2_WEIGHTS = BASE_DIR / "weights" / "smoke_p2" / "best.pt"
BASELINE_WEIGHTS = BASE_DIR / "weights" / "smoke_baseline" / "best.pt"

# Prepare test data YAML (Full test set: 732 images)
full_test_yaml = DATASET_DIR / "full_test_data.yaml"
full_test_yaml.write_text(f"""path: {DATASET_DIR.as_posix()}
train: images/train
val: images/test
test: images/test

nc: 1
names: ['smoke']
""", encoding="utf-8")

# Prepare clean test data YAML (Clean test set: 378 images)
clean_test_yaml = DATASET_DIR / "clean_test_data.yaml"
clean_test_yaml.write_text(f"""path: {DATASET_DIR.as_posix()}
train: images/train
val: clean_test.txt
test: clean_test.txt

nc: 1
names: ['smoke']
""", encoding="utf-8")


def evaluate_split(model, model_name, yaml_path, split_name, img_count):
    print(f"\n>>> Running model.val() for {model_name} on {split_name} ({img_count} images)...", flush=True)
    res = model.val(data=str(yaml_path), split="test", batch=16, imgsz=640, verbose=False)
    
    # Extract metrics
    rd = res.results_dict
    mAP50 = rd.get("metrics/mAP50(B)", res.box.map50)
    mAP50_95 = rd.get("metrics/mAP50-95(B)", res.box.map)
    precision = rd.get("metrics/precision(B)", res.box.p)
    recall = rd.get("metrics/recall(B)", res.box.r)

    print(f"    Results for {model_name} ({split_name}):")
    print(f"      mAP50:     {mAP50:.5f}")
    print(f"      mAP50-95:  {mAP50_95:.5f}")
    print(f"      Precision: {precision:.5f}")
    print(f"      Recall:    {recall:.5f}")

    return {
        "mAP50": mAP50,
        "mAP50_95": mAP50_95,
        "precision": precision,
        "recall": recall,
        "raw_results_dict": rd,
    }


def main():
    print("=" * 75)
    print("  RECONCILING TABLE 4.2 AGGREGATE METRICS VIA model.val() ON TEST SPLITS")
    print("=" * 75)
    print(f"Baseline Checkpoint: {BASELINE_WEIGHTS}")
    print(f"P2 Checkpoint:       {P2_WEIGHTS}")
    print(f"Full Test YAML:      {full_test_yaml}")
    print(f"Clean Test YAML:     {clean_test_yaml}")
    print("-" * 75)

    print("\nLoading models...")
    base_model = YOLO(str(BASELINE_WEIGHTS))
    p2_model = YOLO(str(P2_WEIGHTS))

    results = {}

    # 1. Baseline on Full Test Set (732 images)
    results["base_full"] = evaluate_split(base_model, "YOLOv8s Baseline", full_test_yaml, "Full Test Set", 732)

    # 2. P2 on Full Test Set (732 images)
    results["p2_full"] = evaluate_split(p2_model, "YOLOv8s-P2", full_test_yaml, "Full Test Set", 732)

    # 3. Baseline on Clean Test Set (378 images)
    results["base_clean"] = evaluate_split(base_model, "YOLOv8s Baseline", clean_test_yaml, "Clean Test Subset", 378)

    # 4. P2 on Clean Test Set (378 images)
    results["p2_clean"] = evaluate_split(p2_model, "YOLOv8s-P2", clean_test_yaml, "Clean Test Subset", 378)

    print("\n" + "=" * 75)
    print("                    FINAL RECONCILIATION SUMMARY")
    print("=" * 75)
    print(f"{'Chỉ số':<30} | {'Baseline (Thực)':<15} | {'P2 (Thực)':<15} | {'Báo cáo cũ (Base/P2)':<20}")
    print("-" * 85)

    old_claims = {
        "mAP50 (full test set)": ("0.867", "0.891"),
        "mAP50-95 (full test set)": ("0.541", "0.572"),
        "Recall (full test set)": ("0.823", "0.861"),
        "Precision (full test set)": ("0.879", "0.892"),
        "mAP50 (clean subset)": ("0.854", "0.903"),
        "mAP50-95 (clean subset)": ("--", "--"),
        "Recall (clean subset)": ("--", "--"),
        "Precision (clean subset)": ("--", "--"),
    }

    metrics_map = [
        ("mAP50 (full test set)", results["base_full"]["mAP50"], results["p2_full"]["mAP50"]),
        ("mAP50-95 (full test set)", results["base_full"]["mAP50_95"], results["p2_full"]["mAP50_95"]),
        ("Recall (full test set)", results["base_full"]["recall"], results["p2_full"]["recall"]),
        ("Precision (full test set)", results["base_full"]["precision"], results["p2_full"]["precision"]),
        ("mAP50 (clean subset)", results["base_clean"]["mAP50"], results["p2_clean"]["mAP50"]),
        ("mAP50-95 (clean subset)", results["base_clean"]["mAP50_95"], results["p2_clean"]["mAP50_95"]),
        ("Recall (clean subset)", results["base_clean"]["recall"], results["p2_clean"]["recall"]),
        ("Precision (clean subset)", results["base_clean"]["precision"], results["p2_clean"]["precision"]),
    ]

    for name, base_v, p2_v in metrics_map:
        old_b, old_p = old_claims.get(name, ("--", "--"))
        print(f"{name:<30} | {base_v:<15.4f} | {p2_v:<15.4f} | {old_b} / {old_p}")

    print("=" * 85)


if __name__ == "__main__":
    main()
