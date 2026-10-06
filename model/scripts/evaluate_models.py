import os
import sys
import argparse
import numpy as np
from pathlib import Path

# Ensure UTF-8 output encoding
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "dataset"
DATA_YAML = DATASET_DIR / "data.yaml"

IMG_W = 640
IMG_H = 640

SIZE_BUCKETS = [
    {"name": "< 16x16", "min_area": 0, "max_area": 256},
    {"name": "16-32px", "min_area": 256, "max_area": 1024},
    {"name": "32-48px", "min_area": 1024, "max_area": 2304},
    {"name": "48-64px", "min_area": 2304, "max_area": 4096},
    {"name": "64-96px", "min_area": 4096, "max_area": 9216},
    {"name": "96-128px", "min_area": 9216, "max_area": 16384},
    {"name": ">=128px", "min_area": 16384, "max_area": float("inf")},
]

def calculate_iou(box1, box2):
    """
    Calculate IoU between box1 [x1, y1, x2, y2] and box2 [x1, y1, x2, y2] in pixels.
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area

def eval_bucket_recall(model, image_files, iou_thresh=0.5, conf_thresh=0.25):
    """
    Evaluate Recall broken down by bounding-box size buckets on a given set of image paths.
    """
    bucket_stats = {}
    for b in SIZE_BUCKETS:
        bucket_stats[b["name"]] = {"gt_total": 0, "gt_detected": 0}
    
    # Also summary: <32x32 vs >=32x32
    small_stats = {"gt_total": 0, "gt_detected": 0}
    standard_stats = {"gt_total": 0, "gt_detected": 0}

    total_gt = 0
    total_detected = 0

    for img_path in image_files:
        p = Path(img_path)
        stem = p.stem
        # Corresponding label file
        lbl_file = DATASET_DIR / "labels" / "test" / f"{stem}.txt"
        if not lbl_file.exists():
            # Check valid just in case
            lbl_file = DATASET_DIR / "labels" / "valid" / f"{stem}.txt"
        
        gt_boxes = [] # list of (x1, y1, x2, y2, area)
        if lbl_file.exists():
            content = lbl_file.read_text(encoding="utf-8").strip()
            for line in content.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5:
                    xc = float(parts[1]) * IMG_W
                    yc = float(parts[2]) * IMG_H
                    w = float(parts[3]) * IMG_W
                    h = float(parts[4]) * IMG_H
                    x1 = xc - w / 2
                    y1 = yc - h / 2
                    x2 = xc + w / 2
                    y2 = yc + h / 2
                    area = w * h
                    gt_boxes.append((x1, y1, x2, y2, area))

        if not gt_boxes:
            continue

        total_gt += len(gt_boxes)

        # Run inference on single image
        preds = model.predict(source=str(p), conf=conf_thresh, verbose=False)[0]
        pred_boxes = []
        if preds.boxes is not None and len(preds.boxes) > 0:
            for b in preds.boxes.xyxy.cpu().numpy():
                pred_boxes.append(b)

        # Match each GT box to prediction
        matched_preds = set()
        for gt in gt_boxes:
            gt_bbox = gt[:4]
            area = gt[4]
            is_detected = False

            # Check if any pred box matches this GT box
            best_iou = 0.0
            best_pred_idx = -1
            for idx, pb in enumerate(pred_boxes):
                if idx in matched_preds:
                    continue
                iou = calculate_iou(gt_bbox, pb)
                if iou >= iou_thresh and iou > best_iou:
                    best_iou = iou
                    best_pred_idx = idx

            if best_pred_idx != -1:
                is_detected = True
                matched_preds.add(best_pred_idx)
                total_detected += 1

            # Update buckets
            for b in SIZE_BUCKETS:
                if b["min_area"] <= area < b["max_area"]:
                    bucket_stats[b["name"]]["gt_total"] += 1
                    if is_detected:
                        bucket_stats[b["name"]]["gt_detected"] += 1
                    break

            if area < 1024: # <32x32
                small_stats["gt_total"] += 1
                if is_detected:
                    small_stats["gt_detected"] += 1
            else:
                standard_stats["gt_total"] += 1
                if is_detected:
                    standard_stats["gt_detected"] += 1

    overall_recall = (total_detected / total_gt) if total_gt > 0 else 0.0
    small_recall = (small_stats["gt_detected"] / small_stats["gt_total"]) if small_stats["gt_total"] > 0 else 0.0
    standard_recall = (standard_stats["gt_detected"] / standard_stats["gt_total"]) if standard_stats["gt_total"] > 0 else 0.0

    bucket_results = {}
    for b in SIZE_BUCKETS:
        tot = bucket_stats[b["name"]]["gt_total"]
        det = bucket_stats[b["name"]]["gt_detected"]
        rec = (det / tot) if tot > 0 else 0.0
        bucket_results[b["name"]] = {"total": tot, "detected": det, "recall": rec}

    return {
        "overall_recall": overall_recall,
        "small_recall": small_recall,
        "standard_recall": standard_recall,
        "total_gt": total_gt,
        "total_detected": total_detected,
        "small_stats": small_stats,
        "standard_stats": standard_stats,
        "bucket_results": bucket_results,
    }

def evaluate_model_on_subsets(model_path, model_name="Model"):
    from ultralytics import YOLO
    print(f"\n==================================================")
    print(f"  EVALUATING: {model_name} ({model_path})")
    print(f"==================================================")
    model = YOLO(str(model_path))

    test_img_dir = DATASET_DIR / "images" / "test"
    all_test_images = sorted(list(test_img_dir.glob("*.jpg")))
    
    # Clean test images from file
    clean_test_file = DATASET_DIR / "clean_test.txt"
    if clean_test_file.exists():
        clean_lines = [l.strip() for l in clean_test_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        clean_test_images = [Path(l) for l in clean_lines if Path(l).exists()]
    else:
        clean_test_images = all_test_images

    print(f"Total official test images: {len(all_test_images)}")
    print(f"Total clean test images:    {len(clean_test_images)}")

    # 1. Official Test Set Evaluation
    print("\n--- Running Official Test Set Evaluation ---")
    val_official = model.val(data=str(DATA_YAML), split="test", verbose=False)
    mAP50_official = val_official.results_dict.get("metrics/mAP50(B)", 0.0)
    mAP50_95_official = val_official.results_dict.get("metrics/mAP50-95(B)", 0.0)
    precision_official = val_official.results_dict.get("metrics/precision(B)", 0.0)
    recall_official = val_official.results_dict.get("metrics/recall(B)", 0.0)

    print("Computing size-bucket recall on official test set...")
    official_buckets = eval_bucket_recall(model, all_test_images)

    # 2. Clean Test Subset Evaluation
    print("\n--- Running Clean Test Subset Evaluation ---")
    # Temporary yaml for clean test
    clean_yaml_path = DATASET_DIR / "clean_test_data.yaml"
    clean_yaml_path.write_text(f"""path: {DATASET_DIR.as_posix()}
train: images/train
val: clean_test.txt
test: clean_test.txt

nc: 1
names: ['smoke']
""", encoding="utf-8")

    val_clean = model.val(data=str(clean_yaml_path), split="test", verbose=False)
    mAP50_clean = val_clean.results_dict.get("metrics/mAP50(B)", 0.0)
    mAP50_95_clean = val_clean.results_dict.get("metrics/mAP50-95(B)", 0.0)
    precision_clean = val_clean.results_dict.get("metrics/precision(B)", 0.0)
    recall_clean = val_clean.results_dict.get("metrics/recall(B)", 0.0)

    print("Computing size-bucket recall on clean test set...")
    clean_buckets = eval_bucket_recall(model, clean_test_images)

    return {
        "model_name": model_name,
        "official": {
            "mAP50": mAP50_official,
            "mAP50_95": mAP50_95_official,
            "precision": precision_official,
            "recall": recall_official,
            "buckets": official_buckets,
        },
        "clean": {
            "mAP50": mAP50_clean,
            "mAP50_95": mAP50_95_clean,
            "precision": precision_clean,
            "recall": recall_clean,
            "buckets": clean_buckets,
        },
    }

def print_and_save_report(p2_results, base_results, out_file="evaluation_report.md"):
    report_lines = []
    def log(s=""):
        print(s)
        report_lines.append(s)

    log("# Phase 3: Dual-Metric Evaluation & Ablation Report")
    log()
    log("This report compares the primary **YOLOv8s-P2** model against the baseline **YOLOv8s** (P3-P5).")
    log("Metrics are evaluated across both the **Official Test Set** (732 images, including composites) and the **Clean Subset** (single-subject images only).")
    log()
    log("## 1. Overall Performance Comparison")
    log()
    log("| Metric | YOLOv8s Baseline (Official) | YOLOv8s-P2 (Official) | YOLOv8s Baseline (Clean) | YOLOv8s-P2 (Clean) |")
    log("| :--- | :---: | :---: | :---: | :---: |")
    log(f"| **mAP50** | {base_results['official']['mAP50']:.4f} | {p2_results['official']['mAP50']:.4f} | {base_results['clean']['mAP50']:.4f} | {p2_results['clean']['mAP50']:.4f} |")
    log(f"| **mAP50-95** | {base_results['official']['mAP50_95']:.4f} | {p2_results['official']['mAP50_95']:.4f} | {base_results['clean']['mAP50_95']:.4f} | {p2_results['clean']['mAP50_95']:.4f} |")
    log(f"| **Precision** | {base_results['official']['precision']:.4f} | {p2_results['official']['precision']:.4f} | {base_results['clean']['precision']:.4f} | {p2_results['clean']['precision']:.4f} |")
    log(f"| **Recall (All)** | {base_results['official']['recall']:.4f} | {p2_results['official']['recall']:.4f} | {base_results['clean']['recall']:.4f} | {p2_results['clean']['recall']:.4f} |")
    log()
    log("## 2. Recall by Bounding-Box Size Buckets")
    log()
    log("### A. Summary Buckets (< 32×32 Small Object vs. ≥ 32×32 Standard)")
    log()
    log("| Subset | Size Category | Baseline Recall | P2 Recall | Delta (P2 - Baseline) |")
    log("| :--- | :--- | :---: | :---: | :---: |")
    b_off_sm = base_results['official']['buckets']['small_recall']
    p_off_sm = p2_results['official']['buckets']['small_recall']
    log(f"| **Official Test** | Small (< 32×32) | {b_off_sm*100:.2f}% | {p_off_sm*100:.2f}% | **{'+' if p_off_sm>=b_off_sm else ''}{(p_off_sm-b_off_sm)*100:.2f}%** |")
    b_off_std = base_results['official']['buckets']['standard_recall']
    p_off_std = p2_results['official']['buckets']['standard_recall']
    log(f"| **Official Test** | Standard (≥ 32×32) | {b_off_std*100:.2f}% | {p_off_std*100:.2f}% | **{'+' if p_off_std>=b_off_std else ''}{(p_off_std-b_off_std)*100:.2f}%** |")

    b_cln_sm = base_results['clean']['buckets']['small_recall']
    p_cln_sm = p2_results['clean']['buckets']['small_recall']
    log(f"| **Clean Subset** | Small (< 32×32) | {b_cln_sm*100:.2f}% | {p_cln_sm*100:.2f}% | **{'+' if p_cln_sm>=b_cln_sm else ''}{(p_cln_sm-b_cln_sm)*100:.2f}%** |")
    b_cln_std = base_results['clean']['buckets']['standard_recall']
    p_cln_std = p2_results['clean']['buckets']['standard_recall']
    log(f"| **Clean Subset** | Standard (≥ 32×32) | {b_cln_std*100:.2f}% | {p_cln_std*100:.2f}% | **{'+' if p_cln_std>=b_cln_std else ''}{(p_cln_std-b_cln_std)*100:.2f}%** |")
    log()
    log("### B. Detailed Histogram Size Buckets (Clean Subset)")
    log()
    log("| Bbox Size Bucket | GT Count | Baseline Recall | YOLOv8s-P2 Recall | Delta |")
    log("| :--- | :---: | :---: | :---: | :---: |")
    for b in SIZE_BUCKETS:
        bname = b["name"]
        gt_cnt = p2_results['clean']['buckets']['bucket_results'][bname]['total']
        b_rec = base_results['clean']['buckets']['bucket_results'][bname]['recall']
        p_rec = p2_results['clean']['buckets']['bucket_results'][bname]['recall']
        delta = (p_rec - b_rec) * 100
        log(f"| {bname:<15} | {gt_cnt:>6} | {b_rec*100:6.2f}% | {p_rec*100:6.2f}% | {'+' if delta>=0 else ''}{delta:.2f}% |")
    log()
    out_path = BASE_DIR / out_file
    out_path.write_text("\n".join(report_lines), encoding="utf-8")
    log(f"Report saved to: {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--p2-weights", type=str, default="runs/detect/smoke_p2/weights/best.pt")
    parser.add_argument("--base-weights", type=str, default="runs/detect/smoke_baseline/weights/best.pt")
    parser.add_argument("--out", type=str, default="evaluation_report.md")
    args = parser.parse_args()

    p2_path = BASE_DIR / args.p2_weights
    base_path = BASE_DIR / args.base_weights

    if not p2_path.exists() or not base_path.exists():
        print(f"Error: Weights not found. P2 exists: {p2_path.exists()}, Baseline exists: {base_path.exists()}")
        sys.exit(1)

    p2_eval = evaluate_model_on_subsets(p2_path, "YOLOv8s-P2")
    base_eval = evaluate_model_on_subsets(base_path, "YOLOv8s-Baseline")
    print_and_save_report(p2_eval, base_eval, args.out)
