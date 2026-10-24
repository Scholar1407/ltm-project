import os
import sys
import csv
from pathlib import Path
from PIL import Image
import numpy as np

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent  # model/
PROJECT_ROOT = BASE_DIR.parent
DATASET_DIR = BASE_DIR / "dataset"
TEST_IMG_DIR = DATASET_DIR / "images" / "test"
TEST_LBL_DIR = DATASET_DIR / "labels" / "test"

P2_WEIGHTS = BASE_DIR / "weights" / "smoke_p2" / "best.pt"
BASELINE_WEIGHTS = BASE_DIR / "weights" / "smoke_baseline" / "best.pt"

CLEAN_IDS_FILE = BASE_DIR / "clean_test_ids.txt"
if not CLEAN_IDS_FILE.exists():
    CLEAN_IDS_FILE = DATASET_DIR / "clean_test_ids.txt"

OUTPUT_CSV = BASE_DIR / "weights" / "small_object_recall_comparison.csv"
OUTPUT_FULL_CSV = BASE_DIR / "weights" / "small_object_recall_comparison_full.csv"

# Configuration thresholds
CONF_THRESH = 0.25
IOU_THRESH = 0.50

# Size buckets matching Table 4.1 in report
BUCKETS = [
    {"name": "< 256 px²", "label": "< 256 px² (< 16×16)", "min_area": 0.0, "max_area": 256.0},
    {"name": "256–1024 px²", "label": "256–1024 px² (16×16 – 32×32)", "min_area": 256.0, "max_area": 1024.0},
    {"name": "1024–2304 px²", "label": "1024–2304 px² (32×32 – 48×48)", "min_area": 1024.0, "max_area": 2304.0},
    {"name": "2304–4096 px²", "label": "2304–4096 px² (48×48 – 64×64)", "min_area": 2304.0, "max_area": 4096.0},
    {"name": "4096–9216 px²", "label": "4096–9216 px² (64×64 – 96×96)", "min_area": 4096.0, "max_area": 9216.0},
    {"name": "9216–16384 px²", "label": "9216–16384 px² (96×96 – 128×128)", "min_area": 9216.0, "max_area": 16384.0},
    {"name": "≥ 16384 px²", "label": "≥ 16384 px² (≥ 128×128)", "min_area": 16384.0, "max_area": float("inf")},
]


def calculate_iou(box1, box2):
    """
    Calculate IoU between box1 [x1, y1, x2, y2] and box2 [x1, y1, x2, y2].
    """
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    if union_area <= 0.0:
        return 0.0
    return inter_area / union_area


def parse_ground_truth(label_path, img_width, img_height):
    """
    Parse YOLO normalized labels and convert to pixel coordinates using true image size.
    Returns list of dicts: {'bbox': [x1, y1, x2, y2], 'area': float, 'bucket_idx': int}
    """
    boxes = []
    if not label_path.exists():
        return boxes

    content = label_path.read_text(encoding="utf-8").strip()
    if not content:
        return boxes

    for line in content.splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        # class_id = int(parts[0])
        xc = float(parts[1]) * img_width
        yc = float(parts[2]) * img_height
        w = float(parts[3]) * img_width
        h = float(parts[4]) * img_height

        x1 = xc - w / 2.0
        y1 = yc - h / 2.0
        x2 = xc + w / 2.0
        y2 = yc + h / 2.0
        area = w * h

        # Determine bucket index
        bucket_idx = -1
        for i, b in enumerate(BUCKETS):
            if b["min_area"] <= area < b["max_area"]:
                bucket_idx = i
                break
        if bucket_idx == -1:
            bucket_idx = len(BUCKETS) - 1

        boxes.append({
            "bbox": [x1, y1, x2, y2],
            "area": area,
            "bucket_idx": bucket_idx,
        })
    return boxes


def match_predictions_to_gt(gt_boxes, pred_boxes, pred_confs, iou_thresh=0.5):
    """
    Standard COCO greedy matching:
    Sort predictions by confidence descending.
    For each prediction, match to the unmatched GT box with the highest IoU >= iou_thresh.
    Returns:
        matched_gt_flags: list of bools of length len(gt_boxes)
    """
    matched_gt = set()
    if not gt_boxes or len(pred_boxes) == 0:
        return [False] * len(gt_boxes)

    # Sort prediction indices by confidence descending
    sort_order = np.argsort(-np.array(pred_confs))

    for p_idx in sort_order:
        p_box = pred_boxes[p_idx]
        best_iou = 0.0
        best_gt_idx = -1

        for g_idx, gt in enumerate(gt_boxes):
            if g_idx in matched_gt:
                continue
            iou = calculate_iou(gt["bbox"], p_box)
            if iou >= iou_thresh and iou > best_iou:
                best_iou = iou
                best_gt_idx = g_idx

        if best_gt_idx != -1:
            matched_gt.add(best_gt_idx)

    return [(i in matched_gt) for i in range(len(gt_boxes))]


def evaluate_dataset(image_paths, model_p2, model_baseline, batch_size=16):
    """
    Run evaluation on a collection of image paths for both models.
    """
    # Track statistics per bucket for both models
    num_buckets = len(BUCKETS)
    stats = {
        "baseline": {
            "gt_counts": [0] * num_buckets,
            "tp_counts": [0] * num_buckets,
        },
        "p2": {
            "gt_counts": [0] * num_buckets,
            "tp_counts": [0] * num_buckets,
        },
    }

    # Combined small object stats (<32x32: buckets 0 and 1)
    combined_small = {
        "baseline": {"gt": 0, "tp": 0},
        "p2": {"gt": 0, "tp": 0},
    }

    total_gt = 0
    total_tp = {"baseline": 0, "p2": 0}

    total_images = len(image_paths)
    print(f"Evaluating {total_images} images (conf={CONF_THRESH}, IoU={IOU_THRESH})...")

    # Process in batches for high throughput
    for i in range(0, total_images, batch_size):
        batch_paths = image_paths[i:i + batch_size]
        str_paths = [str(p) for p in batch_paths]

        # Read actual image dimensions and GT
        batch_gts = []
        for p in batch_paths:
            with Image.open(p) as img:
                w, h = img.size
            lbl_path = TEST_LBL_DIR / f"{p.stem}.txt"
            gts = parse_ground_truth(lbl_path, w, h)
            batch_gts.append(gts)

        # Predict baseline
        res_baseline = model_baseline.predict(str_paths, conf=CONF_THRESH, verbose=False)
        # Predict P2
        res_p2 = model_p2.predict(str_paths, conf=CONF_THRESH, verbose=False)

        for b_idx in range(len(batch_paths)):
            gts = batch_gts[b_idx]
            if not gts:
                continue

            # Baseline predictions
            r_base = res_baseline[b_idx]
            base_boxes = r_base.boxes.xyxy.cpu().numpy() if r_base.boxes is not None and len(r_base.boxes) > 0 else []
            base_confs = r_base.boxes.conf.cpu().numpy() if r_base.boxes is not None and len(r_base.boxes) > 0 else []

            base_matches = match_predictions_to_gt(gts, base_boxes, base_confs, iou_thresh=IOU_THRESH)

            # P2 predictions
            r_p2 = res_p2[b_idx]
            p2_boxes = r_p2.boxes.xyxy.cpu().numpy() if r_p2.boxes is not None and len(r_p2.boxes) > 0 else []
            p2_confs = r_p2.boxes.conf.cpu().numpy() if r_p2.boxes is not None and len(r_p2.boxes) > 0 else []

            p2_matches = match_predictions_to_gt(gts, p2_boxes, p2_confs, iou_thresh=IOU_THRESH)

            # Accumulate counts
            for g_i, gt in enumerate(gts):
                b_i = gt["bucket_idx"]
                stats["baseline"]["gt_counts"][b_i] += 1
                stats["p2"]["gt_counts"][b_i] += 1
                total_gt += 1

                if base_matches[g_i]:
                    stats["baseline"]["tp_counts"][b_i] += 1
                    total_tp["baseline"] += 1
                if p2_matches[g_i]:
                    stats["p2"]["tp_counts"][b_i] += 1
                    total_tp["p2"] += 1

                # Combined small (<1024 px²)
                if gt["area"] < 1024.0:
                    combined_small["baseline"]["gt"] += 1
                    combined_small["p2"]["gt"] += 1
                    if base_matches[g_i]:
                        combined_small["baseline"]["tp"] += 1
                    if p2_matches[g_i]:
                        combined_small["p2"]["tp"] += 1

    return stats, combined_small, total_gt, total_tp


def format_table_and_csv(stats, combined_small, total_gt, total_tp, csv_path=None):
    """
    Format statistics into rows, generate Markdown table and write CSV.
    """
    rows = []
    for i, b in enumerate(BUCKETS):
        gt_cnt = stats["baseline"]["gt_counts"][i]
        tp_base = stats["baseline"]["tp_counts"][i]
        tp_p2 = stats["p2"]["tp_counts"][i]

        rec_base = (tp_base / gt_cnt * 100.0) if gt_cnt > 0 else 0.0
        rec_p2 = (tp_p2 / gt_cnt * 100.0) if gt_cnt > 0 else 0.0
        diff_pp = rec_p2 - rec_base

        rows.append({
            "bucket": b["name"],
            "gt_count": gt_cnt,
            "rec_base": rec_base,
            "rec_p2": rec_p2,
            "diff_pp": diff_pp,
            "is_bold": False,
        })

    # Combined small object row (< 32x32 px)
    comb_gt = combined_small["baseline"]["gt"]
    comb_tp_base = combined_small["baseline"]["tp"]
    comb_tp_p2 = combined_small["p2"]["tp"]
    comb_rec_base = (comb_tp_base / comb_gt * 100.0) if comb_gt > 0 else 0.0
    comb_rec_p2 = (comb_tp_p2 / comb_gt * 100.0) if comb_gt > 0 else 0.0
    comb_diff_pp = comb_rec_p2 - comb_rec_base

    comb_row = {
        "bucket": "**< 32×32 px (gộp)**",
        "gt_count": comb_gt,
        "rec_base": comb_rec_base,
        "rec_p2": comb_rec_p2,
        "diff_pp": comb_diff_pp,
        "is_bold": True,
    }
    rows.append(comb_row)

    # Overall total row
    tot_rec_base = (total_tp["baseline"] / total_gt * 100.0) if total_gt > 0 else 0.0
    tot_rec_p2 = (total_tp["p2"] / total_gt * 100.0) if total_gt > 0 else 0.0
    tot_diff_pp = tot_rec_p2 - tot_rec_base
    tot_row = {
        "bucket": "**Tổng cộng (toàn bộ)**",
        "gt_count": total_gt,
        "rec_base": tot_rec_base,
        "rec_p2": tot_rec_p2,
        "diff_pp": tot_diff_pp,
        "is_bold": True,
    }
    rows.append(tot_row)

    # Save to CSV
    if csv_path:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["bucket", "gt_count", "recall_baseline", "recall_p2", "diff_pp"])
            for r in rows:
                b_clean = r["bucket"].replace("**", "")
                writer.writerow([
                    b_clean,
                    r["gt_count"],
                    f"{r['rec_base']:.2f}%",
                    f"{r['rec_p2']:.2f}%",
                    f"{r['diff_pp']:+.2f}pp",
                ])
        print(f"Saved CSV to: {csv_path}")

    # Build Markdown table
    md_lines = [
        "| Bucket kích thước | Số GT boxes | Recall Baseline | Recall P2 | Chênh lệch |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        diff_str = f"{r['diff_pp']:+.2f}pp"
        if r["is_bold"]:
            md_lines.append(
                f"| {r['bucket']} | **{r['gt_count']}** | **{r['rec_base']:.2f}%** | **{r['rec_p2']:.2f}%** | **{diff_str}** |"
            )
        else:
            md_lines.append(
                f"| {r['bucket']} | {r['gt_count']} | {r['rec_base']:.2f}% | {r['rec_p2']:.2f}% | {diff_str} |"
            )
    return "\n".join(md_lines), rows


def main():
    from ultralytics import YOLO

    print("=" * 70)
    print("    EVALUATING SMALL OBJECT RECALL: YOLOv8s-P2 vs YOLOv8s Baseline")
    print("=" * 70)
    print(f"P2 Weights:       {P2_WEIGHTS}")
    print(f"Baseline Weights: {BASELINE_WEIGHTS}")
    print(f"Clean IDs File:   {CLEAN_IDS_FILE}")
    print(f"Confidence Thresh: {CONF_THRESH}")
    print(f"IoU Thresh:        {IOU_THRESH}")
    print("-" * 70)

    # Load models
    print("Loading models into memory...")
    model_p2 = YOLO(str(P2_WEIGHTS))
    model_baseline = YOLO(str(BASELINE_WEIGHTS))

    # 1. Clean test set (Primary official benchmark)
    clean_ids = [line.strip() for line in CLEAN_IDS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    clean_images = []
    for id_ in clean_ids:
        img_p = TEST_IMG_DIR / f"{id_}.jpg"
        if img_p.exists():
            clean_images.append(img_p)

    print(f"\n[1/2] BENCHMARK CHÍNH THỨC — Clean Test Set ({len(clean_images)} images)")
    clean_stats, clean_small, clean_gt, clean_tp = evaluate_dataset(clean_images, model_p2, model_baseline)
    clean_md, clean_rows = format_table_and_csv(clean_stats, clean_small, clean_gt, clean_tp, OUTPUT_CSV)

    print("\n" + "=" * 35 + " KẾT QUẢ BẢNG 4.2 (CLEAN TEST SET) " + "=" * 35)
    print(clean_md)
    print("=" * 105)

    # 2. Full test set (732 images) for reference
    all_test_images = sorted(list(TEST_IMG_DIR.glob("*.jpg")))
    print(f"\n[2/2] THAM KHẢO — Full Test Set ({len(all_test_images)} images)")
    full_stats, full_small, full_gt, full_tp = evaluate_dataset(all_test_images, model_p2, model_baseline)
    full_md, full_rows = format_table_and_csv(full_stats, full_small, full_gt, full_tp, OUTPUT_FULL_CSV)

    print("\n" + "=" * 35 + " KẾT QUẢ BẢNG (FULL TEST SET - 732 ẢNH) " + "=" * 35)
    print(full_md)
    print("=" * 105)

    # Analysis summary for user and report
    comb_row = [r for r in clean_rows if "32×32" in r["bucket"]][0]
    print("\n" + "#" * 70)
    print("               KẾT LUẬN KIỂM TOÁN CHỈ SỐ SMALL OBJECT RECALL")
    print("#" * 70)
    print(f"- Số lượng bounding box < 32×32 px trên Clean Test Set: {comb_row['gt_count']}")
    print(f"- Recall Baseline: {comb_row['rec_base']:.2f}%")
    print(f"- Recall P2:       {comb_row['rec_p2']:.2f}%")
    print(f"- Chênh lệch thực tế: {comb_row['diff_pp']:+.2f} pp")
    
    if comb_row["diff_pp"] >= 10.0:
        print("=> KẾT QUẢ: Claim '+10-18%' ĐƯỢC XÁC NHẬN bởi thực nghiệm.")
    else:
        print(f"=> KẾT QUẢ: Claim '+10-18%' KHÔNG ĐỨNG VỮNG trên thực nghiệm (chênh lệch thực tế là {comb_row['diff_pp']:+.2f} pp).")
        print("   Báo cáo cần cập nhật lại số liệu thật đo được vào Bảng 2.4 và Bảng 4.2.")
    print("#" * 70)


if __name__ == "__main__":
    main()
