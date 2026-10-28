# BÁO CÁO THỰC NGHIỆM ĐO HIỆU NĂNG GIAO THỨC SAP (PROTOCOL BENCHMARK REPORT)

**Đồ án:** Hệ Thống Cảnh Báo Khói Tòa Nhà Qua Mạng UDP Tùy Biến (Smoke Alert Protocol - SAP)  
**Thời gian thực nghiệm:** 24/10/2026  
**Thư mục làm việc:** `d:\ASM2-scholar\Projects\ltm-project`  
**Mục tiêu kiểm toán:** Đo đạc thực nghiệm định lượng độ trễ truyền gói (latency), độ lệch chuẩn (std dev), số vòng phát lại NACK (NACK rounds), và tỷ lệ thành công của giao thức SAP dưới các mức mất gói ngẫu nhiên (packet loss) có kiểm soát, thay thế khoảng ước lượng cảm tính (80–200ms, 350–600ms) trong Bảng 4.4 của báo cáo.

---

## 1. THIẾT LẬP THỰC NGHIỆM & PHƯƠNG PHÁP LUẬN

### 1.1. Bản chất Môi trường Đo Kiểm (Academic Integrity Note)
> [!IMPORTANT]
> **Ghi chú bắt buộc:** Số liệu được đo bằng script `benchmark_performance.py` trên môi trường kiểm thử fault-injection tất định (in-process, loopback qua giao tiếp UDP cục bộ 127.0.0.1). Số liệu này phản ánh **overhead nội tại của cơ chế độ tin cậy ở tầng giao thức SAP** (thời gian phân mảnh, kích hoạt inactivity timer 300ms của Receiver, đóng gói NACK và truyền phát lại có chọn lọc), **KHÔNG PHẢI độ trễ lan truyền vật lý trên đường truyền cáp/Wi-Fi của mạng LAN**.

### 1.2. Dữ liệu thử nghiệm
- **Ảnh kiểm thử:** Ảnh JPEG thật trích xuất từ tập kiểm thử `model/dataset/images/test/`, kích thước **55.979 bytes (~54.67 KB)**, tương ứng đúng **40 chunks SAP** (`MAX_PAYLOAD = 1400 bytes`).
- **Các mức mất gói (Loss Rates):** `[0%, 5%, 10%, 15%, 20%, 25%, 30%]`.
- **Số lượt chạy (Trials):** **N = 30 runs độc lập** cho mỗi mức loss rate (tổng cộng **210 trials**).
- **Cơ chế gây nhiễu:** Lớp socket wrapper `ProbabilisticFaultSocket` chặn các gói tin `CHUNK` ở phía Sender và loại bỏ ngẫu nhiên theo phân phối Bernoulli với seed PRNG độc lập cho từng trial (`seed = 1000 * loss_pct + trial`).
- **Tham số giao thức SAP:**
  - Sender wait timeout: `0.5s` (500ms)
  - Receiver inactivity timeout: `0.3s` (300ms)
  - Max retry limit: `5 lần`

---

## 2. KẾT QUẢ THỰC NGHIỆM ĐO ĐẠC

*Dữ liệu xuất ra file CSV:* [network/tests/benchmark_results.csv](network/tests/benchmark_results.csv)

### Bảng 4.4 Thực nghiệm: Đánh giá hiệu năng và độ tin cậy của Giao thức SAP

| Tỉ lệ mất gói | Latency TB (ms) | Độ lệch chuẩn | Số round NACK TB | Tỉ lệ thành công |
|---|---|---|---|---|
| **0%** | **6.8 ms** | ±2.9 ms | **0.00** | **100.0%** |
| **5%** | **366.5 ms** | ±152.6 ms | **0.97** | **100.0%** |
| **10%** | **539.4 ms** | ±209.4 ms | **1.43** | **100.0%** |
| **15%** | **716.7 ms** | ±317.6 ms | **1.93** | **100.0%** |
| **20%** | **782.9 ms** | ±269.2 ms | **2.10** | **100.0%** |
| **25%** | **965.8 ms** | ±301.7 ms | **2.60** | **100.0%** |
| **30%** | **1395.8 ms** | ±1180.8 ms | **3.60** | **100.0%** |

---

## 3. PHÂN TÍCH HỌC THUẬT & QUY LUẬT HIỆU NĂNG

1. **Trạng thái lý tưởng (Happy Path - 0% loss):**
   - Độ trễ chỉ **6.8 ms** với 0 round NACK. Cho thấy khi đường truyền thông suốt, overhead phân mảnh 40 chunks, tính toán 41 mã kiểm tra CRC32 (40 chunks + 1 toàn ảnh) và truyền qua tầng UDP diễn ra gần như tức thì.
2. **Quy luật bậc thang theo Inactivity Timer (300ms/vòng NACK):**
   - Khi có mất gói, Receiver phải đợi hết `inactivity_timeout = 300ms` tính từ chunk cuối cùng nhận được để xác nhận không còn gói tin nào đang bay trên đường truyền trước khi gửi bản tin NACK.
   - Do đó, độ trễ trung bình tăng tỷ lệ thuận với số round NACK:
     - 5% loss: ~1 round NACK $\rightarrow$ Latency ~ 366.5 ms ($\approx 300\text{ms} + \text{RTT}$).
     - 10% loss: ~1.4 round NACK $\rightarrow$ Latency ~ 539.4 ms.
     - 15% loss: ~1.9 round NACK $\rightarrow$ Latency ~ 716.7 ms.
     - 20% loss: ~2.1 round NACK $\rightarrow$ Latency ~ 782.9 ms.
     - 25% loss: ~2.6 round NACK $\rightarrow$ Latency ~ 965.8 ms.
     - 30% loss: ~3.6 round NACK $\rightarrow$ Latency ~ 1395.8 ms.
3. **Độ tin cậy tuyệt đối (100% Success Rate):**
   - Ở mọi mức mất gói từ 0% đến 30%, toàn bộ **210/210 trials** đều hoàn thành lắp ghép thành công với mã CRC32 trùng khớp 100% so với ảnh gốc. Cơ chế selective retransmission với tối đa 5 lần thử lại đảm bảo khả năng sống sót rất cao trước các xung đột nhiễu đường truyền.

---

## 4. HƯỚNG DẪN CẬP NHẬT TRỰC TIẾP VÀO BÁO CÁO ĐỒ ÁN

### 4.1. Cập nhật Bảng 4.4 (Chương 4.3)
Thay thế toàn bộ các khoảng ước lượng cảm tính `80-200ms` và `350-600ms` bằng bảng số liệu tại **Mục 2** ở trên.

### 4.2. Bổ sung chú thích minh bạch nguồn gốc dưới chân Bảng 4.4
Thêm ghi chú sau ngay dưới Bảng 4.4:
> *\*(Nguồn: Đo lường thực nghiệm bằng test harness `network/tests/benchmark_performance.py` với N=30 trials/mức loss rate trên ảnh mẫu 54.7 KB (40 chunks SAP) qua loopback socket fault-injection. Phản ánh chi phí thời gian của cơ chế Selective NACK Retransmission và timer 300ms ở tầng ứng dụng, chưa bao gồm RTT vật lý của hạ tầng mạng LAN).\**

---
**Tệp script kiểm chứng:** [network/tests/benchmark_performance.py](network/tests/benchmark_performance.py)  
**File kết quả CSV:** [network/tests/benchmark_results.csv](network/tests/benchmark_results.csv)  
**Lệnh thực thi lại:** `python -m network.tests.benchmark_performance`
