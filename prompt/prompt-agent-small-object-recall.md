# PROMPT CHO AGENT — Viết script đo Recall theo kích thước bounding box

## Bối cảnh

Báo cáo đang claim YOLOv8s-P2 có "Small Object Recall: Significantly Higher
(+10-18%)" so với baseline, nhưng con số này CHƯA TỪNG ĐƯỢC ĐO — nó là suy
luận từ kiến trúc, không phải kết quả thực nghiệm. Số liệu aggregate thật
(từ evaluate_models.py trước đó) cho thấy P2 và Baseline gần như ngang nhau
ở Recall và mAP50-95 toàn tập test. Cần đo riêng Recall cho nhóm object nhỏ
để biết claim này có đứng vững hay phải viết lại.

## Việc cần làm

Viết file `model/scripts/evaluate_small_object_recall.py`.

### Input
- 2 checkpoint: `model/weights/smoke_p2/best.pt` và
  `model/weights/smoke_baseline/best.pt`
- Tập test: dùng đúng `clean_test_ids.txt` (378 ảnh single-subject) làm
  benchmark chính — đây là tập đã được audit sạch composite/collage.
  (Có thể in thêm số liệu trên full test set 732 ảnh để so sánh, nhưng
  clean subset là số liệu chính thức đưa vào báo cáo.)
- Label format: YOLO txt (class x_center y_center width height, normalized)

### Logic

1. Với mỗi ảnh trong clean_test_ids.txt:
   - Chạy inference cả 2 model (giữ nguyên conf threshold đã dùng khi train/eval,
     mặc định 0.25 nếu không có config khác)
   - Parse GT boxes từ label file, convert normalized → pixel dùng kích thước
     ảnh thật (đọc từ file ảnh, KHÔNG giả định cố định 640×640 nếu ảnh gốc
     khác kích thước)
2. Bucket GT boxes theo diện tích, DÙNG ĐÚNG các mốc đã có trong Bảng 4.1:
   - `< 256 px²` (< 16×16)
   - `256–1024 px²` (16×16 – 32×32)
   - `1024–2304 px²` (32×32 – 48×48)
   - `2304–4096 px²` (48×48 – 64×64)
   - `4096–9216 px²` (64×64 – 96×96)
   - `9216–16384 px²` (96×96 – 128×128)
   - `≥ 16384 px²` (≥ 128×128)
3. Matching GT ↔ prediction: IoU ≥ 0.5, single class nên không cần check
   nhãn, greedy matching chuẩn kiểu COCO (mỗi GT chỉ match 1 prediction,
   mỗi prediction chỉ dùng 1 lần).
4. Recall mỗi bucket = TP / (TP + FN), tính RIÊNG cho từng model.
5. Tính thêm 1 dòng gộp: **"< 32×32 px (combined small object, <1024px²)"**
   — đây là con số quyết định đúng/sai cho claim "+10-18%" trong Bảng 2.4.

### Output

- File CSV: `model/weights/small_object_recall_comparison.csv` với cột:
  `bucket, gt_count, recall_baseline, recall_p2, diff_pp`
- In ra terminal một bảng Markdown sẵn để dán thẳng vào Bảng 4.2, format:

```
| Bucket kích thước | Số GT boxes | Recall Baseline | Recall P2 | Chênh lệch |
|---|---|---|---|---|
| < 256 px² | ... | ...% | ...% | +/-...pp |
| ... | | | | |
| **< 32×32 px (gộp)** | ... | ...% | ...% | **+/-...pp** |
```

### QUAN TRỌNG

- KHÔNG làm tròn hay "nắn" số liệu để khớp với claim "+10-18%" đã có sẵn
  trong báo cáo cũ. In đúng số đo được, dù nó phủ định claim cũ.
- Nếu thư viện nào (vd `supervision`, `torchmetrics`) đã có sẵn trong
  requirements.txt hỗ trợ size-stratified recall, ưu tiên dùng để tránh
  bug tự viết IoU matching tay. Nếu không có, viết thủ công bằng
  numpy/torch, không cần cài thêm dependency nặng.
- Báo lại rõ: conf threshold dùng là bao nhiêu, IoU threshold là bao nhiêu
  (phải khớp đúng threshold mAP50 dùng, tức IoU=0.5) để số liệu có thể
  đối chứng lại được.
