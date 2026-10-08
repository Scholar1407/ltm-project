# 🚬 Hướng Dẫn Thực Nghiệm & Báo Cáo Demo (SAP Demo Runbook)
### Đề tài: Hệ thống Cảnh Báo Hút Thuốc Tòa Nhà qua Giao Thức Mạng Tùy Biến (Smoke Alert Protocol - SAP)
**Học phần:** Lập trình mạng (Network Programming)

---

## 📌 1. Tổng Quan Kiến Trúc 3 Tầng Thực Nghiệm

Hệ thống được thiết kế theo đúng quy chuẩn bài toán Lập trình mạng mức thấp (Raw UDP Sockets), chia làm 3 tầng độc lập:

```
[Camera / Video Stream]
         │
         ▼
[YOLOv8s-P2 Model] (Loaded once, Conf >= 0.5)
         │  (Event Cooldown: 8s)
         ▼
[Producer-Consumer Queue] ──(Decoupled, zero video freezing)
         │
         ▼
[SmokeAlertSender] ────────► [UDP Socket: Port 5005] ────────► [SmokeAlertReceiver]
  - Split chunks <= 1400B      (Clumsy Fault Injection)        - Per-chunk CRC32 verify
  - META / CHUNK packets                                        - 300ms Inactivity timer
  - Wait window (500ms)                                         - Selective NACK packet
  - Selective retransmit                                        - Whole-image CRC32 verify
                                                                - Trigger Emergency UI
```

1. **Layer 1: Happy-path Live Demo (Đường truyền chuẩn)**: Camera/Video $\to$ Nhận diện hút thuốc $\to$ Đóng gói SAP $\to$ Truyền UDP $\to$ Tái lập ảnh không lỗi $\to$ Kích hoạt chuông/bảng cảnh báo đỏ tại máy Receiver.
2. **Layer 2: Resilience Demo (Thực nghiệm chịu lỗi với Clumsy)**: Sử dụng công cụ bên ngoài OS (Clumsy / WinDivert) can thiệp rớt gói ở tầng mạng (Drop 15–20%). Không can thiệp code Python để đảm bảo tính khách quan 100%. Chứng minh cơ chế NACK selective retransmission.
3. **Layer 3: Automated Test (Bộ kiểm thử tự động pytest)**: Kiểm thử tất định (deterministic) với `FaultInjectingSocket`, chứng minh tái lập dữ liệu trùng khớp từng byte (byte-for-byte fidelity) và vượt qua kiểm tra CRC32.

---

## 🚀 2. Hướng Dẫn Chạy Từng Tầng Demo

### Tầng 1: Happy-path Live Demo (Giao diện đồ họa UI)

#### Bước 1: Khởi động Trạm giám sát trung tâm (Receiver Node)
Mở một cửa sổ Terminal (PowerShell / Command Prompt):
```powershell
# Kích hoạt môi trường ảo
.venv\Scripts\activate

# Khởi chạy Receiver UI
python ui/receiver_ui.py
```
* **Màn hình Receiver hiển thị:** Trạng thái nền xanh `🟢 ALL ZONES SECURED — LISTENING FOR ALERTS`, cổng UDP `5005`, khung hiển thị ảnh và terminal log gói tin thời gian thực.

#### Bước 2: Khởi động Trạm phát hiện tại hiện trường (Sender Node)
Mở cửa sổ Terminal thứ hai:
```powershell
.venv\Scripts\activate

# Khởi chạy Sender UI
python ui/sender_ui.py
```
* **Thao tác Demo:**
  - Nhấn nút **📹 Webcam** (hoặc **📂 Open Video**) rồi nhấn **▶ Start Stream**.
  - Hoặc bấm nút **🚨 Trigger Alert Frame** để tạo ngay một khung hình sự kiện hút thuốc mẫu.
* **Hiện tượng quan sát được:**
  - Khi phát hiện người hút thuốc, camera vẽ khung đỏ (`smoke 0.88`).
  - Bộ đếm Cooldown chuyển sang `Cooldown: Active (8.0s)` để ngăn chặn việc spam cảnh báo hàng trăm lần mỗi giây.
  - Phía Receiver lập tức nhấp nháy đỏ rực `🚨 CRITICAL ALERT: SMOKE DETECTED IN BUILDING!`, hiển thị toàn bộ ảnh chụp hiện trường có đóng dấu thời gian, mã sự kiện (`#1001`), và xác nhận `CRC32 Check: PASSED ✓`.
  - Trên cả 2 màn hình, cột log gói tin hiển thị ăn khớp:
    ```
    [SEND] META   img_id=1001  total=24   crc=0x9f2a1b00
    [SEND] CHUNK  img_id=1001  seq=000/24 size=1400 B crc=0x12a4b3c0
    ...
    [RECV] CHUNK  img_id=1001  seq=023/24 ✓
    [SEND] ACK    img_id=1001  — transfer complete (24/24)
    [RECV] ACK    img_id=1001  — transfer complete (24/24, 0 retransmit rounds)
    ```

---

### Tầng 2: Resilience Demo (Mô phỏng mạng mất gói với Clumsy)

> **Mục đích:** Chứng minh tính bền bỉ của giao thức tùy biến SAP trên UDP mà không dùng TCP.

#### Bước 1: Cài đặt và cấu hình Clumsy trên Windows
1. Tải công cụ mã nguồn mở [Clumsy (WinDivert)](https://jagt.github.io/clumsy/).
2. Chạy `clumsy.exe` với quyền Administrator.
3. Nhập bộ lọc Filter:
   ```
   udp and (udp.DstPort == 5005 or udp.SrcPort == 5005)
   ```
4. Đánh dấu tích vào ô **Drop**, cấu hình tỷ lệ rớt gói: **15.0%** (hoặc 20.0%).
5. Bấm nút **Start** trên Clumsy.

#### Bước 2: Kích hoạt gửi sự kiện cảnh báo
Trên giao diện **Sender UI**, bấm nút **🚨 Trigger Alert Frame**.

#### Bước 3: Thuyết minh nhật ký gói tin (Narration Script)
Chỉ cho Giảng viên thấy quy trình tự phục hồi diễn ra trên Terminal Log:

1. **Sender phát META và các CHUNK:**
   ```
   [SEND] META   img_id=1002  total=24   crc=0x3e18a902
   [SEND] CHUNK  img_id=1002  seq=000/24 size=1400 B crc=...
   [SEND] CHUNK  img_id=1002  seq=005/24 size=1400 B crc=...   <-- BỊ CLUMSY DROP
   [SEND] CHUNK  img_id=1002  seq=012/24 size=1400 B crc=...   <-- BỊ CLUMSY DROP
   ```

2. **Receiver phát hiện thiếu gói sau cửa sổ 300ms:**
   - Sau khi nhận các chunk khác, receiver chờ 300ms mà chưa thấy slot 5 và 12 đến.
   - Timer hết hạn, Receiver chủ động gửi **NACK**:
   ```
   [SEND] NACK   img_id=1002  missing=[005,012]
   ```

3. **Sender nhận NACK và truyền lại chọn lọc (Selective Retransmission):**
   - Sender không gửi lại toàn bộ 24 gói mà chỉ gửi đúng 2 gói bị mất:
   ```
   [RECV] NACK   img_id=1002  missing=[005,012] -> retransmitting
   [SEND] CHUNK  img_id=1002  seq=005/24 size=1400 B crc=...
   [SEND] CHUNK  img_id=1002  seq=012/24 size=1400 B crc=...
   ```

4. **Receiver lấp đầy buffer và xác thực toàn vẹn:**
   - Receiver tính lại CRC32 toàn ảnh: khớp 100% với giá trị ghi trong META ban đầu.
   - Receiver phát ACK hoàn tất:
   ```
   [SEND] ACK    img_id=1002  — transfer complete (24/24)
   [RECV] ACK    img_id=1002  — transfer complete (24/24, 1 retransmit round)
   ```
   - Ảnh hiện trường bung lên sắc nét, không hề có hiện tượng vỡ hình hay lệch khung.

---

### Tầng 3: Automated Reliability Test (Pytest)

> **Dành cho chấm điểm tự động / Báo cáo thực nghiệm độc lập.**

Chạy lệnh kiểm thử tự động:
```powershell
.venv\Scripts\python.exe -m pytest -v network/tests/test_reliability.py
```

Kết quả kỳ vọng (100% Passed):
```
network/tests/test_reliability.py::test_protocol_pack_unpack PASSED               [ 20%]
network/tests/test_reliability.py::test_nack_payload_serialization PASSED        [ 40%]
network/tests/test_reliability.py::test_happy_path_transmission PASSED            [ 60%]
network/tests/test_reliability.py::test_selective_loss_and_nack_retransmission PASSED [ 80%]
network/tests/test_reliability.py::test_corrupted_chunk_dropped_and_recovered PASSED  [100%]

============================== 5 passed in 0.92s ==============================
```

*Bài test `test_selective_loss_and_nack_retransmission` giả lập drop chính xác chunk số 5 và chunk số 20 ở lượt gửi đầu tiên, assert byte-for-byte và xác nhận chính xác 1 hiệp retransmission.*

---

## 💡 3. Các Điểm Sáng Kỹ Thuật Trả Lời Vấn Đáp (Q&A)

1. **Tại sao dùng UDP mà không dùng TCP socket có sẵn?**
   - *Trả lời:* TCP ẩn giấu toàn bộ việc phân mảnh và truyền lại bên trong nhân hệ điều hành. Mục tiêu môn Lập trình mạng là tự tay thiết kế và kiểm soát tầng giao vận (Transport Layer): định dạng Header nhị phân (`struct`), phân mảnh MTU (`<=1400B`), đánh số tuần tự (`seq/total`), phát hiện mất gói và cơ chế phản hồi chọn lọc (`NACK`).
2. **Cơ chế chống nghẽn và ngập lụt cảnh báo (Alert Flooding)?**
   - *Trả lời:* Người hút thuốc trong 10 giây ở tốc độ 30fps sẽ tạo ra ~300 khung hình. Nếu gửi liên tục sẽ làm nghẽn băng thông và treo UI. Hệ thống sử dụng kỹ thuật **Event-based Cooldown (8 giây)**: một hành vi hút thuốc chỉ kích hoạt đúng 1 lần truyền cho đến khi qua 8 giây.
3. **Tại sao dùng hàng đợi Producer-Consumer (`queue.Queue`)?**
   - *Trả lời:* Việc truyền lại gói UDP khi mạng lag có thể mất từ 500ms đến 2.5s. Nếu gọi hàm gửi trực tiếp trong luồng camera, video sẽ bị khựng/đơ (lag freeze). Hàng đợi tách rời (decouple) luồng inference AI và luồng mạng giúp camera luôn đạt 30 FPS mượt mà.
