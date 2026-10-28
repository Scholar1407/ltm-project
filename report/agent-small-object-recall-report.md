# BÁO CÁO THỰC NGHIỆM ĐO RECALL THEO KÍCH THƯỚC BOUNDING BOX (SMALL OBJECT RECALL REPORT)

**Đồ án:** Hệ Thống Cảnh Báo Khói Tòa Nhà Qua Mạng UDP Tùy Biến (Smoke Alert Protocol - SAP)  
**Thời gian thực nghiệm:** 24/10/2026  
**Thư mục làm việc:** `d:\ASM2-scholar\Projects\ltm-project`  
**Mục tiêu kiểm toán:** Đo đạc thực nghiệm chỉ số Recall theo kích thước bounding box để kiểm tra tính chính xác của claim: *"Small Object Recall: Significantly Higher (+10-18%)"* của mô hình YOLOv8s-P2 so với YOLOv8s Baseline trong Bảng 2.4 và Bảng 4.2.

---

## 1. THIẾT LẬP THỰC NGHIỆM & PHƯƠNG PHÁP LUẬN

### 1.1. Dữ liệu & Checkpoint đầu vào
- **Mô hình P2:** [model/weights/smoke_p2/best.pt](model/weights/smoke_p2/best.pt) (160 layers, 10.6M params, 36.9 GFLOPs).
- **Mô hình Baseline:** [model/weights/smoke_baseline/best.pt](model/weights/smoke_baseline/best.pt) (129 layers, 11.1M params, 28.6 GFLOPs).
- **Tập Benchmark chính thức (Clean Test Set):** [model/clean_test_ids.txt](model/clean_test_ids.txt) gồm **378 ảnh single-subject** đã được audit làm sạch các ảnh ghép/collage đa khung hình.
- **Tập đối chứng mở rộng (Full Test Set):** 732 ảnh test trong thư mục `model/dataset/images/test`.
- **Nhãn kiểm thử (Ground Truth):** Chuẩn YOLO txt (`class xc yc w h` normalized), được giải mã động theo kích thước ảnh thực tế bằng `PIL.Image`.

### 1.2. Tham số & Thuật toán Matching
- **Confidence Threshold:** `conf = 0.25` (ngưỡng tiêu chuẩn khi đánh giá mô hình YOLO).
- **IoU Threshold:** `IoU = 0.50` (khớp chính xác với ngưỡng đánh giá của chỉ số `mAP50`).
- **Cơ chế Matching:** Greedy matching chuẩn COCO (đơn lớp). Các hộp dự đoán (predictions) được sắp xếp giảm dần theo điểm tin cậy (confidence), sau đó ghép cặp tuần tự với hộp Ground Truth chưa ghép có IoU lớn nhất $\ge 0.50$. Mỗi Ground Truth chỉ match tối đa 1 prediction và ngược lại.
- **Công thức Recall theo bucket:**
  $$\text{Recall}_{\text{bucket}} = \frac{\text{TP}_{\text{bucket}}}{\text{GT}_{\text{bucket}}}$$
  $$\text{Chênh lệch (pp)} = (\text{Recall}_{\text{P2}} - \text{Recall}_{\text{Baseline}}) \times 100$$

### 1.3. Phân vùng kích thước Bounding Box (Khớp Bảng 4.1 trong Báo cáo)
1. `< 256 px²` (< 16×16 px)
2. `256–1024 px²` (16×16 – 32×32 px)
3. `1024–2304 px²` (32×32 – 48×48 px)
4. `2304–4096 px²` (48×48 – 64×64 px)
5. `4096–9216 px²` (64×64 – 96×96 px)
6. `9216–16384 px²` (96×96 – 128×128 px)
7. `≥ 16384 px²` (≥ 128×128 px)
8. **`< 32×32 px (gộp)` (< 1024 px²):** Chỉ số quyết định kiểm chứng vật thể nhỏ.

---

## 2. KẾT QUẢ THỰC NGHIỆM ĐO ĐẠC

### 2.1. Bảng số liệu chính thức trên Tập Kiểm thử Sạch (Clean Test Set — 378 ảnh)
*Dữ liệu xuất ra file: [model/weights/small_object_recall_comparison.csv](model/weights/small_object_recall_comparison.csv)*

| Bucket kích thước | Số GT boxes | Recall Baseline | Recall P2 | Chênh lệch |
|---|---|---|---|---|
| < 256 px² | 10 | 20.00% | 10.00% | -10.00pp |
| 256–1024 px² | 81 | 46.91% | 45.68% | -1.23pp |
| 1024–2304 px² | 107 | 59.81% | 63.55% | +3.74pp |
| 2304–4096 px² | 71 | 56.34% | 70.42% | +14.08pp |
| 4096–9216 px² | 93 | 76.34% | 74.19% | -2.15pp |
| 9216–16384 px² | 30 | 73.33% | 83.33% | +10.00pp |
| ≥ 16384 px² | 37 | 91.89% | 91.89% | +0.00pp |
| **< 32×32 px (gộp)** | **91** | **43.96%** | **41.76%** | **-2.20pp** |
| **Tổng cộng (toàn bộ)** | **429** | **63.17%** | **66.20%** | **+3.03pp** |

---

### 2.2. Bảng số liệu tham khảo trên Toàn bộ Tập Kiểm thử (Full Test Set — 732 ảnh)
*Dữ liệu xuất ra file: [model/weights/small_object_recall_comparison_full.csv](model/weights/small_object_recall_comparison_full.csv)*

| Bucket kích thước | Số GT boxes | Recall Baseline | Recall P2 | Chênh lệch |
|---|---|---|---|---|
| < 256 px² | 64 | 50.00% | 53.12% | +3.12pp |
| 256–1024 px² | 290 | 74.83% | 74.48% | -0.34pp |
| 1024–2304 px² | 293 | 77.82% | 80.89% | +3.07pp |
| 2304–4096 px² | 241 | 83.40% | 85.48% | +2.07pp |
| 4096–9216 px² | 335 | 89.55% | 88.96% | -0.60pp |
| 9216–16384 px² | 216 | 90.74% | 93.98% | +3.24pp |
| ≥ 16384 px² | 354 | 96.61% | 96.05% | -0.56pp |
| **< 32×32 px (gộp)** | **354** | **70.34%** | **70.62%** | **+0.28pp** |
| **Tổng cộng (toàn bộ)** | **1793** | **84.55%** | **85.55%** | **+1.00pp** |

---

## 3. KẾT LUẬN KIỂM TOÁN HỌC THUẬT

### 3.1. Đánh giá tính chính xác của Claim
- **Tuyên bố trong báo cáo cũ:** *"Small Object Recall: Significantly Higher (+10-18%)"*.
- **Kết quả thực nghiệm:** **CLAIM NÀY KHÔNG ĐỨNG VỮNG.**
  - Trên **Clean Test Set (chuẩn)**: Nhóm vật thể nhỏ `< 32×32 px` có **91 ground-truth boxes**. Recall của Baseline đạt **43.96%**, trong khi P2 đạt **41.76%** (P2 thực tế thấp hơn **-2.20 pp**).
  - Trên **Full Test Set**: Nhóm vật thể nhỏ `< 32×32 px` có **354 ground-truth boxes**. Recall của P2 và Baseline gần như ngang nhau tuyệt đối (**70.62% vs 70.34%**, chỉ chênh lệch **+0.28 pp**).

### 3.2. Điểm mạnh thực tế của Kiến trúc YOLOv8s-P2
Dù không tăng đột biến ở nhóm siêu nhỏ (<32px) như suy luận lý thuyết ban đầu, đầu dò P2 (feature map 160×160, stride 4) mang lại những cải thiện rõ rệt ở dải kích thước trung bình và tổng thể:
1. **Tăng mạnh ở nhóm 48×48 đến 64×64 px:** Nhóm diện tích `2304–4096 px²` tăng vọt **+14.08 pp** (P2 đạt 70.42% so với 56.34% của Baseline).
2. **Tăng mạnh ở nhóm 96×96 đến 128×128 px:** Nhóm diện tích `9216–16384 px²` tăng **+10.00 pp** (P2 đạt 83.33% so với 73.33% của Baseline).
3. **Cải thiện Recall tổng thể:** Trên toàn bộ 429 bounding boxes của tập Clean Test, Recall tổng thể của P2 đạt **66.20%**, cao hơn Baseline (**63.17%**) là **+3.03 pp**.

---

## 4. HƯỚNG DẪN CẬP NHẬT TRỰC TIẾP VÀO BÁO CÁO ĐỒ ÁN

### 4.1. Cập nhật Bảng 2.4 (So sánh sơ bộ kiến trúc)
*Sửa dòng Recall object < 32px:*
- **Cũ:** Baseline = *"Baseline"*, P2 = *"+10-18%"*, Chênh lệch = *"+10-18%"*
- **Sửa thành:** 
  - Baseline = **`44.0%`**
  - YOLOv8s-P2 = **`41.8%`**
  - Chênh lệch = **`-2.2 pp`** *(hoặc ghi chú: Tương đương ở <32px, tăng +14.1 pp ở dải 48-64px)*

### 4.2. Cập nhật Bảng 4.2 (Hiệu năng chi tiết theo kích thước)
Dán trực tiếp bảng số liệu tại **Mục 2.1** vào Bảng 4.2 của báo cáo, thay thế các dấu gạch ngang `"-"` và chữ `"Baseline"` định tính bằng các giá trị đo đạc định lượng chính xác:
- Hàng `< 32×32 px (gộp)`: **Baseline = 43.96%**, **P2 = 41.76%**, **Chênh lệch = -2.20 pp**.
- Bổ sung nhận xét học thuật trung thực: *"Việc bổ sung tầng P2 giúp mạng giữ lại các đặc trưng biên sắc nét hơn, tạo ra bước nhảy vọt ở nhóm vật thể kích thước trung bình (tăng +14.08 pp ở dải 48–64px và +10.00 pp ở dải 96–128px), nâng tổng Recall toàn tập kiểm thử lên 66.20% (+3.03 pp). Tuy nhiên, với các vật thể siêu nhỏ dưới 32px, độ phân giải cao cũng đi kèm việc tăng độ nhạy với nhiễu nền, khiến tỷ lệ Recall ở phân khúc này duy trì ở mức tương đương Baseline (-2.20 pp)."*

---
**Tệp script kiểm chứng:** [model/scripts/evaluate_small_object_recall.py](model/scripts/evaluate_small_object_recall.py)  
**Lệnh tái hiện kết quả:** `python model/scripts/evaluate_small_object_recall.py`
