# 🚬 Hướng Dẫn Thực Nghiệm & Báo Cáo Demo (SAP Demo Runbook)
### Đề tài: Hệ thống Cảnh Báo Hút Thuốc Tòa Nhà qua Giao Thức Mạng Tùy Biến (Smoke Alert Protocol - SAP)
**Học phần:** Lập trình mạng (Network Programming)

---

## 📌 1. Kiến Trúc Luồng Dữ Liệu & 3 Tầng Minh Chứng Thực Nghiệm

### A. Kiến Trúc Luồng Dữ Liệu (Data-flow Architecture)
Hệ thống được thiết kế theo đúng quy chuẩn bài toán Lập trình mạng mức thấp (Raw UDP Sockets), tách biệt hoàn toàn giữa tác vụ xử lý AI và truyền dẫn mạng:

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
  - Split chunks <= 1400B      (Clumsy Fault Injection)        - Bind 0.0.0.0:5005
  - META / CHUNK packets                                        - Per-chunk CRC32 verify
  - Wait window (500ms)                                         - 300ms Inactivity timer
  - Selective retransmit                                        - Selective NACK packet
  - Fan-out to N receivers                                      - Whole-image CRC32 verify
  - (1 worker/socket per node)                                  - Keyed by (sender_addr, img_id)
                                                                - Trigger Emergency UI
```

### B. 3 Tầng Minh Chứng Thực Nghiệm (Demo Evidence Layers)
Khi báo cáo đồ án, buổi demo được tổ chức thành 3 tầng minh chứng rõ ràng:

| Tầng Minh Chứng | Mục Đích (Purpose) | Tính Bắt Buộc | Thời Điểm Thực Hiện |
| :--- | :--- | :---: | :--- |
| **Tầng 1: Happy-path Live Demo** | Chứng minh đường truyền chuẩn trên mạng LAN thật (hoặc loopback): nhận diện hút thuốc, phân mảnh UDP, tái lập ảnh tức thì và kích hoạt báo động tại Receiver. | **Bắt buộc** | Thực hiện trực tiếp đầu tiên khi bắt đầu báo cáo với Giảng viên. |
| **Tầng 2: Resilience Demo (Clumsy)** | Can thiệp rớt gói mạng (Drop 15–20%) bằng công cụ hệ điều hành Clumsy; chứng minh cơ chế NACK Selective Retransmission tự phục hồi mà không dùng TCP. | **Tùy chọn nhưng nên có** | Thực hiện ngay sau Tầng 1 để ghi điểm tối đa về độ tin cậy giao thức. |
| **Tầng 3: Automated Tests (Pytest)** | Bộ kiểm thử tự động tất định (deterministic): giả lập rớt gói chính xác, hỏng CRC32, truyền đa trạm (multi-receiver) và dung lỗi khi có trạm chết. | **Báo cáo thực nghiệm** | Chạy trước buổi báo cáo; chụp màn hình kết quả 7/7 PASSED đưa vào slide/báo cáo. |

---

## 📋 2. Checklist Chuẩn Bị Demo Trên 2 Laptop (LAN Environment)

Trước ngày báo cáo hoặc trước khi lên thuyết minh với 2 laptop thật (Laptop A: Sender có webcam, Laptop B: Receiver trạm trực), thực hiện đầy đủ các bước chuẩn bị sau:

1. **Kết nối cùng mạng LAN / Wi-Fi**:
   - Cả 2 laptop phải cùng kết nối vào một Access Point (cùng dải mạng subnet IPv4).
   - Kiểm tra địa chỉ IPv4 của Laptop B (Receiver): Xem trực tiếp trên banner màu xanh của giao diện `Receiver UI` (hoặc mở CMD gõ `ipconfig`).
   - Trên Laptop A (Sender), mở CMD gõ lệnh kiểm tra thông mạng: `ping <IP_Laptop_B>`. Đảm bảo nhận được phản hồi `Reply from...`.

2. **Cấu hình Windows Firewall trên Laptop B (Receiver)**:
   - Windows Firewall mặc định có thể chặn các gói tin UDP lạ đến từ mạng ngoài.
   - Mở PowerShell / CMD bằng quyền **Administrator** trên Laptop B và chạy lệnh:
     ```powershell
     netsh advfirewall firewall add rule name="SAP UDP 5005" dir=in action=allow protocol=UDP localport=5005 profile=private
     ```
   - Đảm bảo profile mạng của card Wi-Fi/LAN được đặt là **Private network** (trong Windows Settings > Network & Internet > Properties), không để Public network.

3. **Lưu ý về Wi-Fi AP / Client Isolation (Trường học / Công cộng)**:
   - Nhiều mạng Wi-Fi trường học hoặc quán café bật tính năng *AP Isolation* (ngăn các laptop trong mạng nói chuyện với nhau). Nếu `ping` không thông dù đã tắt Firewall:
   - **Giải pháp dự phòng (Fallback):** Dùng điện thoại bật **Mobile Hotspot** cho 2 laptop cùng kết nối vào, hoặc cắm trực tiếp 1 sợi dây cáp mạng LAN (Ethernet cable) giữa 2 laptop.

4. **Vị trí chạy công cụ Clumsy**:
   - Khi thực hiện Tầng 2, Clumsy chỉ cần chạy trên **MỘT** laptop duy nhất (thường là máy Sender Laptop A), mở bằng quyền **Administrator** với bộ lọc UDP cổng 5005.

5. **Dry-run (Tổng duyệt)**:
   - Chạy thử toàn bộ kịch bản từ Tầng 1 đến Tầng 2 trên 2 laptop thật ít nhất 1 lần vào ngày hôm trước để tránh lỗi bất ngờ trong phòng thi.

---

## 🚀 3. Hướng Dẫn Thực Hiện Từng Tầng Demo

### Tầng 1: Happy-path Live Demo (Giao diện đồ họa UI trên 2 Laptop)

#### Bước 1: Khởi động Trạm giám sát trung tâm (Laptop B - Receiver Node)
Mở Terminal trên Laptop B:
```powershell
# Kích hoạt môi trường ảo
.venv\Scripts\activate

# Khởi chạy Receiver UI
python ui/receiver_ui.py
```
* **Màn hình Receiver hiển thị:** 
  - Banner xanh: `🟢 ALL ZONES SECURED — LISTENING FOR ALERTS`.
  - Dòng thông tin IP: `🌐 Local LAN IPv4 for Sender: 192.168.1.X (Port 5005)`.
  - Terminal log sẵn sàng lắng nghe gói tin trên `0.0.0.0:5005`.

#### Bước 2: Khởi động Trạm phát hiện tại hiện trường (Laptop A - Sender Node)
Mở Terminal trên Laptop A:
```powershell
.venv\Scripts\activate

# Khởi chạy Sender UI
python ui/sender_ui.py
```
* **Thao tác cấu hình mạng:**
  - Nhập địa chỉ IP của Laptop B vào ô **Receivers (host:port)**: `192.168.1.X:5005` (nếu demo nhiều trạm nhận, nhập danh sách phân cách bởi dấu phẩy, ví dụ: `192.168.1.X:5005, 192.168.1.Y:5005`).
  - Nhấn nút **Apply**.
* **Thao tác Demo cảnh báo:**
  - Nhấn **📹 Webcam** (hoặc **📂 Open Video**) rồi nhấn **▶ Start Stream**.
  - Hoặc bấm nút **🚨 Trigger Alert Frame** để tạo khung hình phát hiện hút thuốc mẫu tức thì.
* **Hiện tượng quan sát được:**
  - Khi phát hiện người hút thuốc, camera vẽ khung đỏ (`smoke 0.88`).
  - Bộ đếm Cooldown chuyển sang `Cooldown: Active (8.0s)` để ngăn chặn việc spam cảnh báo hàng trăm lần mỗi giây.
  - Phía Receiver (Laptop B) lập tức nhấp nháy đỏ rực `🚨 CRITICAL ALERT: SMOKE DETECTED IN BUILDING!`, hiển thị toàn bộ ảnh chụp hiện trường có đóng dấu thời gian, mã sự kiện (`#1001`), và xác nhận `CRC32 Check: PASSED ✓`.
  - Trên cả 2 màn hình, cột log gói tin hiển thị ăn khớp có gắn địa chỉ peer rõ ràng:
    ```
    [SEND] META   -> 192.168.1.X:5005     img_id=1001  total=24   crc=0x9f2a1b00
    [SEND] CHUNK  -> 192.168.1.X:5005     img_id=1001  seq=000/024 size=1400 B crc=0x12a4b3c0
    ...
    [RECV] CHUNK  <- 192.168.1.A:54321    img_id=1001  seq=023/024 [OK]
    [SEND] ACK    -> 192.168.1.A:54321    img_id=1001  -- transfer complete (24/24)
    [RECV] ACK    <- 192.168.1.X:5005     img_id=1001  -- transfer complete (24/24, 0 retransmit rounds)
    ```

---

### Tầng 2: Resilience Demo (Mô phỏng mạng mất gói với Clumsy)

> **Mục đích:** Chứng minh tính bền bỉ của giao thức tùy biến SAP trên UDP mà không dùng TCP.

#### Bước 1: Cài đặt và cấu hình Clumsy trên Windows
1. Tải công cụ mã nguồn mở [Clumsy (WinDivert)](https://jagt.github.io/clumsy/).
2. Chạy `clumsy.exe` với quyền **Administrator** (trên máy Laptop A).
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
   [SEND] META   -> 192.168.1.X:5005     img_id=1002  total=24   crc=0x3e18a902
   [SEND] CHUNK  -> 192.168.1.X:5005     img_id=1002  seq=000/024 size=1400 B crc=...
   [SEND] CHUNK  -> 192.168.1.X:5005     img_id=1002  seq=005/024 size=1400 B crc=...   <-- BỊ CLUMSY DROP
   [SEND] CHUNK  -> 192.168.1.X:5005     img_id=1002  seq=012/024 size=1400 B crc=...   <-- BỊ CLUMSY DROP
   ```

2. **Receiver phát hiện thiếu gói sau cửa sổ inactivity 300ms:**
   - Sau khi nhận các chunk khác, Receiver chờ 300ms mà chưa thấy slot 5 và 12 đến.
   - Timer hết hạn, Receiver chủ động gửi **NACK**:
   ```
   [SEND] NACK   -> 192.168.1.A:54321    img_id=1002  missing=[005,012]
   ```

3. **Sender nhận NACK và truyền lại chọn lọc (Selective Retransmission):**
   - Sender không gửi lại toàn bộ 24 gói mà chỉ gửi đúng 2 gói bị mất:
   ```
   [RECV] NACK   <- 192.168.1.X:5005     img_id=1002  missing=[005,012] -> retransmitting
   [SEND] CHUNK  -> 192.168.1.X:5005     img_id=1002  seq=005/024 size=1400 B crc=...
   [SEND] CHUNK  -> 192.168.1.X:5005     img_id=1002  seq=012/024 size=1400 B crc=...
   ```

4. **Receiver lấp đầy buffer và xác thực toàn vẹn:**
   - Receiver tính lại CRC32 toàn ảnh: khớp 100% với giá trị ghi trong META ban đầu.
   - Receiver phát ACK hoàn tất:
   ```
   [SEND] ACK    -> 192.168.1.A:54321    img_id=1002  -- transfer complete (24/24)
   [RECV] ACK    <- 192.168.1.X:5005     img_id=1002  -- transfer complete (24/24, 1 retransmit round)
   ```
   - Ảnh hiện trường bung lên sắc nét, không hề có hiện tượng vỡ hình hay lệch khung.

---

### Tầng 3: Automated Reliability Tests (Pytest)

> **Dành cho chấm điểm tự động / Báo cáo thực nghiệm độc lập.**

Chạy lệnh kiểm thử tự động toàn diện:
```powershell
.venv\Scripts\python.exe -m pytest -v network/tests/test_reliability.py
```

Kết quả kỳ vọng (100% Passed - 9/9 tests):
```
network/tests/test_reliability.py::test_protocol_pack_unpack PASSED               [ 11%]
network/tests/test_reliability.py::test_nack_payload_serialization PASSED        [ 22%]
network/tests/test_reliability.py::test_happy_path_transmission PASSED            [ 33%]
network/tests/test_reliability.py::test_selective_loss_and_nack_retransmission PASSED [ 44%]
network/tests/test_reliability.py::test_corrupted_chunk_dropped_and_recovered PASSED  [ 55%]
network/tests/test_reliability.py::test_multi_receiver_selective_loss PASSED      [ 66%]
network/tests/test_reliability.py::test_multi_receiver_dead_node_tolerance PASSED [ 77%]
network/tests/test_reliability.py::test_stdlib_only_imports_in_cores PASSED       [ 88%]
network/tests/test_reliability.py::test_cli_loopback_and_notify_cmd PASSED       [100%]

============================== 9 passed in 3.36s ==============================
```

*Các ca kiểm thử tự động chứng minh:*
- `test_selective_loss_and_nack_retransmission`: Giả lập drop chính xác chunk số 5 và 20 ở lượt gửi đầu, assert byte-for-byte và xác nhận đúng 1 hiệp retransmission.
- `test_corrupted_chunk_dropped_and_recovered`: Giả lập payload bị biến đổi bit (bit flip), Receiver phát hiện sai CRC chunk và drop ngay tại tầng socket, sau đó tự hồi phục qua NACK.
- `test_multi_receiver_selective_loss`: Sender phát ảnh tới 2 Receiver đồng thời; Receiver 1 đường truyền sạch (0 retransmission), Receiver 2 bị rớt gói; cả 2 đều nhận ảnh toàn vẹn và chỉ Receiver 2 thực hiện retransmit.
- `test_multi_receiver_dead_node_tolerance`: Sender gửi cho 2 Receiver trong đó 1 Receiver đã chết/tắt nguồn; trạm sống vẫn nhận trọn vẹn ảnh mà không bị treo hay nghẽn.
- `test_stdlib_only_imports_in_cores`: Xác thực toàn bộ core và CLI chỉ phụ thuộc vào thư viện chuẩn (stdlib) của Python, hoạt động hoàn hảo khi chặn hoàn toàn tkinter, cv2, numpy, PIL và ultralytics.
- `test_cli_loopback_and_notify_cmd`: Kiểm thử toàn vẹn cả Receiver CLI và Sender CLI qua loopback với file JPEG mẫu và cơ chế thực thi `--notify-cmd` kèm thay thế tham số.

---

## 🔍 4. Phân Tích Gói Tin Bằng Wireshark (Wireshark Deep-dive)

Khi báo cáo môn Lập trình mạng, việc mở Wireshark bắt trực tiếp gói tin trên card mạng sẽ thuyết phục hoàn toàn Giảng viên:

### A. Thiết lập Bắt Gói Tin
1. Mở Wireshark. Chọn card mạng đang kết nối thực tế (**Wi-Fi** hoặc **Ethernet Adapter** khi dùng 2 laptop).
   *(Lưu ý: Nếu chạy thử trên cùng 1 máy tính qua IP 127.0.0.1, cần chọn card **Npcap Loopback Adapter**).*
2. Nhập bộ lọc hiển thị (Display Filter):
   ```wireshark
   udp.port == 5005
   ```
   Hoặc lọc chính xác giao thức tùy biến SAP bằng chuỗi magic bytes:
   ```wireshark
   frame contains "SAP1"
   ```

### B. Cách Đọc Header Nhị Phân 19-byte Trong Hex Dump
Click vào một gói tin SAP bất kỳ và quan sát cửa sổ **Packet Bytes (Hex Dump)**. Vị trí 19 bytes đầu tiên của UDP Payload là cấu trúc Header SAP:

| Byte Offset | Độ Dài | Trường (Field) | Giá Trị Mẫu Hex | Ý Nghĩa Thực Tế |
| :--- | :---: | :--- | :--- | :--- |
| `0x00 - 0x03` | 4 bytes | `magic` | `53 41 50 31` | Chuỗi ASCII `"SAP1"` nhận diện giao thức |
| `0x04` | 1 byte | `type` | `01` hoặc `02` | `01` = META, `02` = CHUNK, `03` = ACK, `04` = NACK |
| `0x05 - 0x08` | 4 bytes | `img_id` | `00 00 03 E9` | Mã sự kiện ảnh (Ví dụ `1001` = `0x03E9`) |
| `0x09 - 0x0A` | 2 bytes | `seq` | `00 05` | Thứ tự phân mảnh chunk (Ví dụ seq = `5`) |
| `0x0B - 0x0C` | 2 bytes | `total` | `00 18` | Tổng số phân mảnh (Ví dụ total = `24`) |
| `0x0D - 0x0E` | 2 bytes | `payload_len` | `05 78` | Độ dài payload (Ví dụ `1400` bytes = `0x0578`) |
| `0x0F - 0x12` | 4 bytes | `crc32` | `9F 2A 1B 00` | Mã CRC32 kiểm tra toàn vẹn (Big-Endian uint32) |

### C. Những Điểm Nhấn Thuyết Minh Cho Giảng Viên Trên Wireshark
1. **Gói META phát đầu tiên:** Cho thấy kích thước chỉ gồm 19 bytes header + chuỗi timestamp trong payload, báo trước cho Receiver biết `total` chunks và `crc32` tổng thể.
2. **Kích thước gói CHUNK luôn `<= 1419 bytes`:** 1400B payload + 19B header = 1419B (cộng thêm 8B UDP header và 20B IP header = 1447B `<= 1500B MTU chuẩn), đảm bảo không bao giờ bị phân mảnh ở tầng IP (IP Fragmentation).
3. **Khi bật Clumsy:**
   - Chỉ cho Giảng viên thấy gói tin `NACK` (Type `04`) gửi từ Receiver về Sender với danh sách các số seq bị thiếu.
   - Ngay sau đó thấy đúng các sequence đó được gửi lại từ Sender (Selective Retransmit) thay vì gửi lại toàn bộ từ đầu.
   - Cuối cùng là gói `ACK` (Type `03`) xác nhận giao dịch thành công.

---

## 💡 5. Các Điểm Sáng Kỹ Thuật Trả Lời Vấn Đáp (Q&A)

### 1. Tại sao dùng UDP mà không dùng TCP socket có sẵn?
- **Bản chất giao vận:** UDP là giao thức phi kết nối (connectionless), không đảm bảo thứ tự gói tin và không có cơ chế truyền lại tích hợp; nhờ vậy UDP có overhead rất thấp và độ trễ tối thiểu. Lưu ý rằng UDP vẫn có checksum ở tầng transport để loại bỏ các datagram bị lỗi bit, do đó thách thức thực tế trên UDP là hiện tượng mất gói (packet loss) và đảo thứ tự (packet reordering), chứ không phải lỗi ngầm không kiểm soát.
- **Những gì SAP bổ sung bên trên UDP:** 
  - Phân mảnh dữ liệu nhỏ hơn MTU mạng (`<=1400B`).
  - Đánh số tuần tự (`seq / total`).
  - Kiểm tra tính toàn vẹn 2 lớp: CRC32 cho từng chunk và CRC32 toàn thể bức ảnh.
  - Phản hồi chọn lọc NACK (Selective NACK) và chỉ truyền lại đúng các gói bị mất.
  - Giới hạn số lần thử lại (bounded retries: tối đa 5 lần) kèm timeout tĩnh để tránh kẹt vô hạn.
- **Lý do chọn UDP:** Chúng em chọn UDP **vì mục tiêu học tập (learning objective)** của môn Lập trình mạng: TCP làm toàn bộ công việc phân mảnh, buffer và truyền lại ẩn bên trong nhân hệ điều hành (kernel). Việc tự thiết kế giao thức tùy biến SAP trên UDP giúp chúng em trực tiếp hiểu sâu và làm chủ các cơ chế cốt lõi của tầng giao vận (Transport Layer).
- **Góc nhìn thực tế công nghiệp:** Trong một hệ thống thương mại thực tế chỉ cần gửi từng ảnh cảnh báo đơn lẻ, TCP (hoặc giao thức QUIC hiện đại) thông thường sẽ là sự lựa chọn kỹ thuật tối ưu và sẵn có; việc tự hiện thực hóa độ tin cậy (reliability) trên UDP chỉ thực sự cần thiết trong bối cảnh học tập, hoặc khi cần tối ưu hóa độ trễ cực thấp trong multicast/broadcast.

### 2. Cơ chế chống nghẽn và ngập lụt cảnh báo (Alert Flooding)?
- Người hút thuốc trong 10 giây ở tốc độ 30fps sẽ tạo ra ~300 khung hình. Nếu gửi liên tục sẽ làm nghẽn băng thông và treo UI. Hệ thống sử dụng kỹ thuật **Event-based Cooldown (8 giây)**: một hành vi hút thuốc chỉ kích hoạt đúng 1 lần truyền cho đến khi qua 8 giây.

### 3. Tại sao dùng hàng đợi Producer-Consumer (`queue.Queue`)?
- Việc truyền lại gói UDP khi mạng lag có thể mất từ 500ms đến 2.5s. Nếu gọi hàm gửi trực tiếp trong luồng camera, video sẽ bị khựng/đơ (lag freeze). Hàng đợi tách rời (decouple) luồng inference AI và luồng mạng giúp camera luôn đạt 30 FPS mượt mà.

### 4. Hạn chế của giao thức SAP hiện tại (Protocol Limitations)?
Khi được hỏi về khả năng mở rộng trong tương lai, nêu trung thực các hạn chế hiện tại của SAP:
1. **Chưa có Congestion Control:** Chưa có cơ chế điều khiển tắc nghẽn động như TCP AIMD hoặc BBR để tự động giảm tốc độ truyền khi mạng của tòa nhà bị nghẽn.
2. **Chưa có Flow Control:** Chưa có cửa sổ trượt động (sliding window) phản ánh dung lượng bộ nhớ đệm còn trống của bên nhận.
3. **Chưa có Encryption / Authentication:** Dữ liệu payload truyền dạng nhị phân rõ ràng, chưa mã hóa AES/TLS và chưa có chữ ký số xác thực danh tính để chống kẻ xấu giả mạo gói tin cảnh báo (spoofing).
4. **Đa trạm bằng Multiple Unicast:** Hiện tại việc gửi cho nhiều trạm nhận (building-wide notification) được thực hiện bằng mô hình 1 socket / 1 worker độc lập cho từng trạm nhận (N-unicast sockets). Chưa tối ưu bằng IP Multicast ở tầng mạng.
5. **Cơ chế Selective-NACK ARQ đơn giản hóa:** Phụ thuộc vào các mốc timeout tĩnh (inactivity 300ms, wait window 500ms), chưa tính toán và cập nhật thời gian RTT động (Round-Trip Time Estimation) như TCP RTO.

---

## 📱 6. Phụ Lục: Kiểm Thử Với Điện Thoại Thay Cho Laptop Thứ Hai (Test with a Phone Instead of a 2nd Laptop)

Nhờ kiến trúc tách rời (Headless CLI Core chỉ dùng thư viện chuẩn Python `stdlib`), hệ thống SAP có thể chạy trực tiếp trên **điện thoại Android (qua Termux)** để đóng vai trò làm trạm nhận (Receiver) hoặc trạm gửi (Sender) độc lập khi bạn chưa có sẵn chiếc laptop thứ hai để kiểm thử mạng LAN.

### Bước 1: Cài đặt môi trường trên điện thoại (Termux)
1. Tải và cài đặt ứng dụng **Termux** từ [F-Droid](https://f-droid.org/en/packages/com.termux/) hoặc [GitHub Releases](https://github.com/termux/termux-app/releases) *(Lưu ý: Không cài từ Google Play Store vì bản đó đã ngừng cập nhật từ lâu)*.
2. Mở Termux và cài đặt Python:
   ```bash
   pkg update && pkg install python
   ```
3. *(Tùy chọn nhận thông báo pop-up)*: Cài ứng dụng **Termux:API** trên điện thoại và cài gói bổ trợ trong terminal:
   ```bash
   pkg install termux-api
   ```
4. Chạy lệnh chống ngủ ngầm (giúp Termux tiếp tục lắng nghe UDP khi tắt màn hình):
   ```bash
   termux-wake-lock
   ```

### Bước 2: Chuyển mã nguồn và khởi động Receiver CLI trên điện thoại
1. Copy thư mục `network/` của dự án vào bộ nhớ máy hoặc Termux (chỉ cần các file mạng: `network/__init__.py`, `network/shared/`, `network/receiver/`, `network/sender/`).
2. Xem địa chỉ IP của điện thoại trong mạng Wi-Fi:
   ```bash
   ip addr
   ```
   *(Tìm dòng `inet` thuộc interface `wlan0`, ví dụ: `192.168.1.50`)*.
3. Chạy Receiver CLI chế độ dòng lệnh:
   ```bash
   python -m network.receiver.cli --bind 0.0.0.0 --port 5005 --out received/ --notify-cmd "termux-notification --title '🚨 CANH BAO HUT THUOC!' --content 'Phat hien hut thuoc! Event #{img_id}' --image-path '{path}' --action 'termux-open {path}'"
   ```
   - CLI sẽ in ra các IP khả dụng và chờ gói tin trên cổng `5005`.
   - Mỗi khi nhận ảnh hoàn tất, ảnh JPEG tự động lưu vào `received/`, bắn thông báo Android hiển thị trực tiếp ảnh chụp hiện trường trên màn hình notification, và bấm vào thông báo sẽ tự động mở xem ảnh toàn màn hình!

### Bước 3: Chiều kiểm thử xuôi (Forward Test: Laptop gửi -> Điện thoại nhận)
1. Trên Laptop, mở `ui/sender_ui.py`.
2. Trong ô **Receivers (host:port)**, nhập IP của điện thoại: `192.168.1.50:5005`, bấm **Apply**.
3. Bấm **🚨 Trigger Alert Frame**.
4. **Hiện tượng quan sát:** 
   - Trên Laptop: Terminal hiển thị `[SEND] META` và các gói `[SEND] CHUNK -> 192.168.1.50:5005`.
   - Trên Điện thoại: Màn hình Termux cuộn log `[RECV] CHUNK`, xác thực CRC32 thành công, lưu file ảnh vào `received/` và chuông/thông báo Android rung lên tức thì.
   - Bật Wireshark hoặc Clumsy trên laptop để quan sát cơ chế retransmission khi mạng rớt gói.

### Bước 4: Chiều kiểm thử ngược (Reverse Test: Điện thoại gửi -> Laptop nhận)
Kiểm tra xem laptop đã cấu hình mở Firewall đúng chưa bằng cách để điện thoại làm Sender:
1. Trên Laptop, khởi chạy `ui/receiver_ui.py` (Laptop lắng nghe trên port 5005).
2. Trên Điện thoại, chạy Sender CLI với một ảnh JPEG có sẵn (ví dụ ảnh chụp camera `sample.jpg`):
   ```bash
   python -m network.sender.cli --to 192.168.1.X:5005 --send-file sample.jpg
   ```
   *(Thay `192.168.1.X` bằng địa chỉ LAN IP của laptop)*.
3. **Hiện tượng quan sát:**
   - Nếu Laptop UI lập tức nhấp nháy đỏ và hiển thị ảnh: Windows Firewall trên laptop đã được mở đúng quy tắc.
   - Nếu Sender CLI trên điện thoại báo timeout/retry: Laptop đang bị Firewall chặn gói tin UDP vào cổng 5005.

### Bước 5: Biến thể dùng Wi-Fi Hotspot (Hotspot Variant - Tránh AP Isolation)
Nếu Wi-Fi tại trường học bật chế độ AP/Client Isolation (chặn các thiết bị giao tiếp nội bộ):
- Trên điện thoại, bật tính năng **Điểm phát sóng di động (Mobile Hotspot)**.
- Cho Laptop kết nối vào mạng Wi-Fi của điện thoại.
- Địa chỉ IP của điện thoại lúc này thường là IP Gateway mặc định: `192.168.43.1`.
- Giao thức SAP truyền mượt mà 100% không lo bị chặn cổng hay cô lập mạng.

### ⚠️ Lưu ý quan trọng: Những gì phương pháp này KHÔNG kiểm tra được
Thử nghiệm với điện thoại là giải pháp thay thế tuyệt vời để kiểm tra logic mạng LAN và tính năng CLI không phụ thuộc GUI. Tuy nhiên, phương pháp này **không thể kiểm tra:**
- Cấu hình Windows Firewall trên chiếc laptop thứ hai của bạn học.
- Môi trường cài đặt Python, Tkinter và độ phân giải màn hình trên chiếc laptop thứ hai.
- Vì vậy, **trước ngày bảo vệ chính thức**, nhóm vẫn bắt buộc phải thực hiện tổng duyệt (dry-run) một lần trên đúng 2 chiếc laptop thật theo Checklist ở Mục 2.

