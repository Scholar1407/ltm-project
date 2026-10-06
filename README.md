# 🚬 Dự Án Phát Hiện Hành Vi Hút Thuốc (Smoking Detection AI)
### Huấn luyện Mô hình YOLOv8s-P2 & YOLOv8s Baseline (Offline Video Analysis)

Tài liệu này tổng hợp toàn bộ thông tin dự án, kết quả kiểm thử hiện tại và hướng dẫn từng bước để cài đặt, huấn luyện mô hình trên máy tính cá nhân (Local GPU) có card đồ họa NVIDIA.

---

## 1. Thông Tin Hiện Tại & Tiến Độ Dự Án

### 🎯 Mục tiêu
- Huấn luyện mô hình thị giác máy tính nhận diện hành vi hút thuốc (cầm điếu thuốc, đưa tay lên miệng, ngậm thuốc lá) thuộc 1 class duy nhất: `smoke` (ID: 0).
- Tập trung tối đa vào **Recall (độ nhạy) của vật thể nhỏ** thay vì chỉ số mAP thông thường, vì trong các video thực tế góc quay xa, điếu thuốc chỉ chiếm kích thước rất nhỏ ($< 32 \times 32$ px).
- **Kiến trúc lựa chọn:** 
  - **Mô hình chính (Primary):** `YOLOv8s-P2` (bổ sung đầu phát hiện stride-4, feature map $160 \times 160$ giữ lại chi tiết vật thể nhỏ).
  - **Mô hình đối chứng (Baseline):** `YOLOv8s` tiêu chuẩn (3 đầu phát hiện P3–P5, stride 8–32).

---

### 📊 Dữ liệu huấn luyện (Dataset)
- **Nguồn:** Kyunghee University Smoking Detection Dataset (Roboflow, CC BY 4.0).
- **Định dạng:** Chuẩn YOLO (`class_id x_center y_center width height` chuẩn hóa 0–1).
- **Quy mô:** **18,230 ảnh** (640 × 640 px), tổng cộng **25,533 nhãn**:
  - `train`: **16,758 ảnh** (đã qua augmentation lật/xoay)
  - `valid`: **740 ảnh**
  - `test`: **732 ảnh**
- **Cấu hình dữ liệu:** [dataset/data.yaml](file:///d:/ASM2-scholar/Projects/ltm-project/dataset/data.yaml)

---

### 🔍 Kết quả Giai đoạn 0 (Data Audit) — ĐÃ XONG
- Đã chạy phân tích [scripts/audit_composites.py](file:///d:/ASM2-scholar/Projects/ltm-project/scripts/audit_composites.py) và phát hiện: **48.36% tập Test chính thức (354/732 ảnh)** là ảnh ghép dạng collage (2×2 hoặc 3–4 khung hình).
- Đã bóc tách thành công tập chuẩn thực tế **Clean Evaluation Subset (378 ảnh đơn đối tượng)** lưu tại [clean_test_ids.txt](file:///d:/ASM2-scholar/Projects/ltm-project/clean_test_ids.txt) và [clean_valid_ids.txt](file:///d:/ASM2-scholar/Projects/ltm-project/clean_valid_ids.txt).

---

### 🧪 Kết quả Giai đoạn 1 (Dry-Run Sanity Check) — ĐÃ PASSED 100%
- Đã nghiệm thu thành công kịch bản [scripts/run_sanity_check.py](file:///d:/ASM2-scholar/Projects/ltm-project/scripts/run_sanity_check.py) trên 16 mẫu ảnh đơn [dataset/sanity/](file:///d:/ASM2-scholar/Projects/ltm-project/dataset/sanity/):
  - Chuyển giao thành công 389/437 trọng số pretrained backbone từ `yolov8s.pt`.
  - Hàm mất mát (`box_loss`) giảm đều đặn về 0, thuật toán hội tụ mượt mà.
  - Zero lỗi NaN/Inf, dữ liệu và định dạng nhãn hoàn toàn chuẩn xác.
  - Kết quả lưu tại: `runs/detect/sanity_check/`.
- **Đánh giá:** Pipeline đã sẵn sàng tuyệt đối để bước vào huấn luyện đầy đủ 100 Epochs.

---

## 2. Yêu Cầu Phần Cứng Máy Train (Local Machine)

- **Hệ điều hành:** Windows 10/11 hoặc Ubuntu Linux.
- **GPU (Bắt buộc):** NVIDIA GeForce RTX (ví dụ: RTX 3060, 4060, 5060, Legion 5 hoặc tương đương) với tối thiểu **6 GB – 8 GB VRAM**.
- **RAM hệ thống:** $\ge 16 \text{ GB}$.
- **Ổ cứng trống:** $\ge 15 \text{ GB}$ (chứa dataset và các file weights checkpoint).

---

## 3. Hướng Dẫn Cài Đặt Môi Trường Trên Máy Local

Mở terminal (PowerShell hoặc Command Prompt) tại thư mục dự án `ltm-project`:

### Bước 3.1: Tạo và kích hoạt môi trường ảo (Khuyên dùng)
```powershell
# Tạo môi trường ảo python
python -m venv .venv

# Kích hoạt môi trường (trên Windows PowerShell):
.venv\Scripts\Activate.ps1
```
*(Nếu gặp lỗi PowerShell chặn script, chạy lệnh: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rồi kích hoạt lại).*

### Bước 3.2: Cài đặt PyTorch có hỗ trợ CUDA (GPU)
Để tận dụng tối đa sức mạnh của card đồ họa NVIDIA và nhân Tensor Cores, cần cài bản PyTorch có CUDA:
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```
*(Nếu máy dùng CUDA 12.1 hoặc 12.6, bạn có thể thay `cu124` tương ứng).*

### Bước 3.3: Cài đặt các thư viện cần thiết
```powershell
pip install -r requirements.txt
```

### Bước 3.4: Kiểm tra nhận diện GPU
Chạy lệnh kiểm tra xem Python đã nhận diện được Card NVIDIA chưa:
```powershell
python -c "import torch; print('CUDA Ready:', torch.cuda.is_available(), '| GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"
```
👉 **Kết quả mong đợi:** In ra `CUDA Ready: True | GPU: NVIDIA GeForce RTX ...`.

---

## 4. Chi Tiết Các Lệnh Huấn Luyện (Phase 2)

### 🚀 Bước 4.1 (Tùy chọn): Chạy thử Sanity Check nhanh trên GPU máy bạn
Chạy thử 20 epoch trên 16 ảnh test nhỏ để đảm bảo máy bạn không gặp trục trặc (~30 giây):
```powershell
python scripts/run_sanity_check.py --epochs 20 --batch 4
```

---

### 🔥 Bước 4.2: Huấn luyện Mô hình Chính YOLOv8s-P2 (Primary Run)
Huấn luyện 100 epochs trên toàn bộ 16,758 ảnh train:
```powershell
python scripts/train_p2.py --epochs 100 --batch -1
```
- **Ý nghĩa cấu hình:**
  - `--batch -1`: Kích hoạt chế độ **Auto-batch** của Ultralytics, tự động dò tìm batch size tối ưu dựa trên VRAM hiện tại của card đồ họa (tránh lỗi Out-of-Memory).
  - Tự động bật `amp=True` (Automatic Mixed Precision FP16) tận dụng Tensor Cores của dòng card RTX.
  - Tự động lưu checkpoint định kỳ **5 epoch một lần** (`save_period=5`) vào thư mục `runs/detect/smoke_p2/weights/`.
  - Tự động dừng sớm (`patience=20`) nếu mô hình đạt đỉnh không tăng thêm sau 20 epoch.

---

### ⚖️ Bước 4.3: Huấn luyện Mô hình Đối chứng YOLOv8s Baseline
Sau khi mô hình P2 chạy xong (hoặc mở cửa sổ terminal thứ 2 nếu card đủ VRAM):
```powershell
python scripts/train_baseline.py --epochs 100 --batch -1
```
- Kết quả lưu tại: `runs/detect/smoke_baseline/`.

---

### 🔄 Cách xử lý nếu bị dừng / ngắt quãng giữa chừng (Resume Strategy)
Nếu máy bị mất điện, cập nhật Windows hoặc bạn chủ động tạm dừng (`Ctrl + C`), Ultralytics cho phép **huấn luyện tiếp tục chính xác từ epoch bị ngắt** mà không phải chạy lại từ đầu:

- **Tiếp tục train P2:**
  ```powershell
  python scripts/train_p2.py --resume
  ```
- **Tiếp tục train Baseline:**
  ```powershell
  python scripts/train_baseline.py --resume
  ```
*(Script sẽ tự động tìm checkpoint `runs/detect/<tên_run>/weights/last.pt` để nối tiếp).*

---

## 5. Đánh Giá & Bóc Tách Recall Bounding Box (Phase 3)

Sau khi cả 2 mô hình đã hoàn tất 100 epochs, chạy script đánh giá để tạo báo cáo so sánh:

```powershell
python scripts/evaluate_models.py --p2-weights runs/detect/smoke_p2/weights/best.pt --base-weights runs/detect/smoke_baseline/weights/best.pt --out evaluation_report.md
```

**Script này sẽ tự động:**
1. Đánh giá trên **Official Test Set (732 ảnh)** $\rightarrow$ Báo cáo mAP50, mAP50-95.
2. Đánh giá trên **Clean Subset (378 ảnh single-subject)** $\rightarrow$ Số liệu phản ánh hiệu năng video thực tế.
3. Bóc tách riêng tỷ lệ **Recall của vật thể nhỏ ($< 32 \times 32$ px)** và xuất ra bảng chênh lệch $\Delta$ chi tiết tại file `evaluation_report.md`.

---

## 6. Danh Sách Các File Cần Gửi Lại Sau Khi Train Xong

Sau khi huấn luyện và đánh giá hoàn tất, bạn chỉ cần nén và gửi lại các file kết quả sau (rất nhẹ, chỉ khoảng **~90 MB**):

1. **Trọng số mô hình chính P2:** `runs/detect/smoke_p2/weights/best.pt`
2. **Trọng số mô hình baseline:** `runs/detect/smoke_baseline/weights/best.pt`
3. **Biểu đồ & thông số huấn luyện P2:**
   - `runs/detect/smoke_p2/results.csv`
   - `runs/detect/smoke_p2/results.png`
4. **Biểu đồ & thông số baseline:**
   - `runs/detect/smoke_baseline/results.csv`
   - `runs/detect/smoke_baseline/results.png`
5. **Báo cáo so sánh:** `evaluation_report.md`

*(Toàn bộ các file weights `best.pt` này sau đó sẽ được nạp trực tiếp vào giao diện phân tích video để kiểm thử thực tế).*
