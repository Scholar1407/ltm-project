# 📘 TÀI LIỆU TOÀN DIỆN VỀ KIẾN TRÚC GIAO THỨC SAP & PHÂN TÍCH GÓI TIN WIRESHARK
### Dự án: Hệ Thống Cảnh Báo Hút Thuốc Tòa Nhà Qua Giao Thức Mạng Tùy Biến (Smoke Alert Protocol - SAP)
**Học phần:** Lập trình mạng (Network Programming)

---

## 📌 PHẦN 1: BẢN CHẤT & TÍNH HỌC THUẬT CỦA GIAO THỨC SAP

### 1. Giao thức SAP là gì? Có được cộng đồng công nhận không?
* **Định nghĩa:** **SAP** trong đồ án này là viết tắt của **Smoke Alert Protocol** (Giao thức Cảnh báo Khói / Hút thuốc).
* **Tính học thuật:** Giao thức này **chỉ tồn tại trong phạm vi đồ án môn học**, **KHÔNG** phải là một chuẩn RFC quốc tế (IETF). *(Lưu ý: Trong thực tế thế giới mạng có chuẩn RFC 2974 cũng viết tắt là SAP - Session Announcement Protocol, hoặc hãng phần mềm ERP SAP, nhưng SAP ở đây là tên nhóm tự đặt cho đề tài).*

### 2. Tại sao lại tự thiết kế giao thức SAP trên UDP thay vì dùng TCP?
Đây chính là **mục tiêu đào tạo cốt lõi** của môn học Lập trình mạng:
* **Nếu dùng TCP:** Toàn bộ các công việc phức tạp như chia nhỏ gói tin, đánh số thứ tự, gửi ACK xác nhận, truyền lại khi mất gói đều do nhân hệ điều hành (OS Kernel) làm tự động ẩn bên dưới. Lập trình viên chỉ gọi `send()` và `recv()` như đọc file thông thường, không học được bản chất tầng giao vận.
* **Tự thiết kế SAP trên Raw UDP Socket:** Sinh viên tự tay xây dựng toàn bộ cơ chế của tầng Transport:
  - Tự định nghĩa cấu trúc Header nhị phân 19-byte.
  - Tự phân mảnh dữ liệu (Chunking) nhỏ hơn MTU mạng ($\le 1400$B).
  - Tự kiểm tra toàn vẹn dữ liệu 2 lớp bằng mã băm **CRC32**.
  - Tự hiện thực hóa cơ chế sửa lỗi tin cậy **Selective-NACK ARQ** (chỉ truyền lại đúng gói bị mất).
  - Tự xây dựng cơ chế tự động dò tìm máy trong LAN (**Auto-Discovery**).

---

## 📐 PHẦN 2: CẤU TRÚC HEADER NHỊ PHÂN 19-BYTE CỦA GIAO THỨC SAP

Mọi gói tin của giao thức SAP truyền qua mạng đều bắt đầu bằng phần đầu (Header) nhị phân cố định dài **đúng 19 bytes** (được đóng gói dạng Big-Endian theo chuẩn mạng bằng định dạng `!4sBIHHHI`):

| Offset | Độ dài | Tên trường | Kiểu dữ liệu | Ý nghĩa kỹ thuật |
| :---: | :---: | :--- | :--- | :--- |
| `0x00 - 0x03` | 4 bytes | `magic` | `char[4]` | Chuỗi nhận diện cố định: ASCII **`"SAP1"`** (Hex: `53 41 50 31`). Gói nào không có chữ này sẽ bị loại bỏ ngay tại tầng socket. |
| `0x04` | 1 byte | `pkt_type` | `uint8` | Loại gói tin: `1`=META, `2`=CHUNK, `3`=ACK, `4`=NACK, `5`=BEACON, `6`=PROBE. |
| `0x05 - 0x08` | 4 bytes | `img_id` | `uint32` | Mã sự kiện ảnh (vd `#1001`). Khi là gói BEACON thì tái sử dụng để mang số cổng data (`5005`). |
| `0x09 - 0x0A` | 2 bytes | `seq` | `uint16` | Số thứ tự phân mảnh (`0` đến `total - 1`). |
| `0x0B - 0x0C` | 2 bytes | `total` | `uint16` | Tổng số phân mảnh tạo nên bức ảnh. |
| `0x0D - 0x0E` | 2 bytes | `payload_len` | `uint16` | Chiều dài phần dữ liệu đi kèm đằng sau (tối đa 1400 bytes). |
| `0x0F - 0x12` | 4 bytes | `crc32` | `uint32` | Mã kiểm tra tính toàn vẹn (CRC32 của chunk đó, hoặc CRC32 toàn ảnh trong gói META). |
| `Sau byte 19` | N bytes | `payload` | `bytes` | Dữ liệu thực: Mảnh ảnh JPEG (với CHUNK), chuỗi ngày giờ (với META), danh sách mảnh thiếu (với NACK). |

> **Quy tắc vàng về kích thước gói (MTU Rule):**  
> $1400\text{B (Payload)} + 19\text{B (SAP)} + 8\text{B (UDP)} + 20\text{B (IP)} = 1447\text{B} \le 1500\text{B (MTU chuẩn Ethernet)}$.  
> Giúp các gói tin **tuyệt đối không bao giờ bị phân mảnh ở tầng IP (IP Fragmentation)**, tăng tốc độ truyền tối đa.

---

## 🔄 PHẦN 3: LUỒNG XỬ LÝ TOÀN TRÌNH TỪ KHI NẠP VIDEO ĐẾN KHI NHẬN CẢNH BÁO

Hệ thống hoạt động theo mô hình đa luồng phân tách hoàn toàn (Producer - Consumer) qua 5 giai đoạn:

```
[Video File / Camera]
         │ (OpenCV đọc frame)
         ▼
[Thread A: AI Inference] ──► Chạy YOLOv8s-P2 bắt khói ──► Bộ đếm Cooldown 8s
         │                                                      │ (Có khói & ngoài cooldown)
         ▼                                                      ▼
[frame_queue (maxsize=1)]                               [alert_queue]
         │                                                      │
         ▼                                                      ▼
[Thread B: UI Render]                                   [Sender Network Worker]
(Hiển thị Canvas mượt 30 FPS)                                  │ (Tạo socket/worker riêng cho từng client)
                                                                ▼
                                                [Truyền qua mạng: UDP Port 5005]
                                                (1 Gói META -> N Gói CHUNK)
                                                                │
                                                                ▼
                                                [Receiver Node: Cổng 5005]
                                                (Lắp ráp -> CRC32 -> Gửi ACK -> Báo động)
```

1. **Giai đoạn 1 (Thread A - Chạy nền):** OpenCV giải mã từng khung hình video. Điều tiết tốc độ đọc frame (pacing) đúng FPS gốc. Khung hình được đưa qua AI `YOLOv8s-P2` nhận diện khói. Khung hình vẽ box được đẩy vào `frame_queue (maxsize=1)`.
2. **Giai đoạn 2 (Thread B - Giao diện Tkinter):** Lấy frame mới nhất từ `frame_queue` vẽ lên màn hình với tốc độ chuẩn `FPS: ~30`. Tách biệt luồng giúp video không bao giờ bị đơ/lag kể cả khi mạng bị nghẽn.
3. **Giai đoạn 3 (Cooldown chống ngập lụt):** Khi phát hiện hút thuốc, hàm `trigger_alert()` kích hoạt bộ đếm **Event Cooldown (8 giây)** để không spam hàng trăm ảnh/giây. Đóng dấu banner đỏ, nén thành ảnh JPEG bytes và nạp vào `alert_queue`.
4. **Giai đoạn 4 (Đóng gói & Phát mạng song song):**
   - Sender tính CRC32 của toàn bộ bức ảnh JPEG.
   - Cắt ảnh thành $N$ mảnh (`<= 1400 bytes/mảnh`).
   - Với mỗi máy nhận (lấy từ Auto-Discovery cổng 5006), Sender mở 1 luồng worker + 1 socket UDP riêng:
     - Phát gói **`META`** (báo trước số lượng $N$ mảnh, CRC32 toàn ảnh, timestamp).
     - Phát liên tiếp các gói **`CHUNK 0`** đến **`CHUNK N-1`**.
5. **Giai đoạn 5 (Tái lập ảnh tại Client):**
   - Client nhận `META`: khởi tạo mảng rỗng gồm $N$ vị trí.
   - Nhận từng `CHUNK`: kiểm tra mã CRC32 của riêng chunk đó (sai vứt bỏ ngay). Đúng thì xếp vào vị trí `seq`.
   - Đủ $N$ mảnh: nối lại thành ảnh, tính CRC32 tổng. So khớp 100% với META $\rightarrow$ Client gửi gói **`ACK`** về cho Sender, đồng thời kích hoạt chuông/giao diện đỏ `🚨 CRITICAL ALERT!` và hiện ảnh.

---

## ⚡ PHẦN 4: CƠ CHẾ DUNG LỖI KHI MẠNG MẤT HOẶC CHẬP CHỜN

| Tình huống mạng | Hiện tượng | Cách giao thức SAP xử lý |
| :--- | :--- | :--- |
| **Mất gói chập chờn (Packet Loss 15% - 50%)** | Một số mảnh `CHUNK` bị rớt trên đường truyền Wi-Fi. | Phía Client có bộ đếm **Inactivity Timer (300ms)**: Quá 300ms chưa nhận đủ ảnh, Client chủ động gửi gói **`NACK`** chứa danh sách các số sequence bị thiếu (vd: `missing=[005, 012]`). Sender nhận NACK **chỉ gửi lại đúng 2 chunk đó** (**Selective Retransmission**), không gửi lại cả bức ảnh. |
| **Mất mạng hoàn toàn giữa chừng (Sập nguồn, đứt Wi-Fi)** | Sender không nhận được gói `ACK` từ Client. | Sender chờ gói ACK trong cửa sổ `wait_timeout = 500ms`. Hết giờ tự động gửi lại META và chờ tiếp. Sau **5 lần thử lại (`max_retries = 5`)** thất bại $\rightarrow$ Sender từ bỏ phiên gửi (`[FAIL] Abandoning transfer`). Nhờ chạy 1 worker riêng cho từng client, **1 máy sập không làm ảnh hưởng đến các máy khác, camera vẫn quay 30 FPS bình thường**. |
| **Client thoát ứng dụng / Rút mạng** | Client biến mất khỏi mạng LAN. | Client phát gói `BEACON` định kỳ 5s/lần. Sender giữ thời gian sống **TTL = 30s**. Quá 30s không thấy Client báo danh $\rightarrow$ Sender tự động xóa khỏi danh sách gửi, chấm xanh biến mất. |

---

## 🔬 PHẦN 5: GIẢI MÃ THỰC NGHIỆM TRÊN WIRESHARK (DỰA TRÊN ẢNH CHỤP THỰC TẾ)

Quan sát trực tiếp nhật ký bắt gói tin thực tế của bạn trên Wireshark từ **gói 371 đến 423**:

```text
No.   Time           Source          Destination     Protocol  Length  Info
371   19.205160300   10.20.7.148     10.20.6.50      UDP       80      57412 -> 5005 Len=38   <-- [GÓI 1: META BÁO HIỆU]
372   19.207963100   10.20.7.148     10.20.6.50      UDP       1461    57412 -> 5005 Len=1419 <-- [CHUNK 0]
373   19.210963900   10.20.7.148     10.20.6.50      UDP       1461    57412 -> 5005 Len=1419 <-- [CHUNK 1]
...   ...            ...             ...             ...       ...     ...
421   19.576831200   10.20.7.148     10.20.6.50      UDP       1461    57412 -> 5005 Len=1419 <-- [CHUNK 49]
422   19.580921600   10.20.7.148     10.20.6.50      UDP       806     57412 -> 5005 Len=764  <-- [CHUNK 50: MẢNH CUỐI]
423   19.607666600   10.20.6.50      10.20.7.148     UDP       61      5005 -> 57412 Len=19   <-- [XÁC NHẬN ACK THÀNH CÔNG]
```

### Chính xác là 1 bức ảnh được chia nhỏ ra gửi thành nhiều gói tin:

1. **Gói số 371 — Gói mở đầu `META` (`Len=38`):**
   - Độ dài: 19 byte header SAP + 19 byte chuỗi thời gian (vd: `"2026-10-18 17:35:12"` có đúng 19 ký tự).
   - Nhiệm vụ: Báo cho Client `10.20.6.50` biết sắp có 1 bức ảnh gồm tổng cộng **51 mảnh** và cung cấp mã CRC32 chuẩn của toàn bộ bức ảnh.
2. **Gói số 372 đến gói số 422 — Các gói dữ liệu `CHUNK`:**
   - Tổng cộng có đúng **51 mảnh ảnh** ($422 - 372 + 1 = 51$).
   - Từ gói 372 đến 421: Mỗi mảnh mang đúng `1400 bytes` dữ liệu ảnh + 19 bytes header = `Len=1419`.
   - Gói số 422: Là mảnh đuôi cuối cùng của ảnh, mang phần dữ liệu còn dư `745 bytes` + 19 bytes header = `Len=764`.
3. **Gói số 423 — Gói xác nhận `ACK` (`Len=19`):**
   - Client nhận đủ 51 mảnh, ghép lại thành file JPEG hoàn chỉnh, kiểm tra CRC32 khớp 100%.
   - Client gửi gói ACK dài đúng 19 byte về cho Laptop: Giao dịch thành công trọn vẹn!

### Soi chi tiết Hex Dump tại gói `395` (Một mảnh CHUNK mẫu):
Ở khung dưới gói tin 395:
```text
0020   ... 53 41 50 31 02 00 00 03 ed 00 17 00 33 05 78 f2 ff 13 a2
```
* `53 41 50 31`: Mã ASCII `"SAP1"`.
* `02`: `pkt_type = 2` (Gói **CHUNK**).
* `00 00 03 ed`: `img_id = 1005` (Hex `0x03ed` = 1005).
* `00 17`: Số thứ tự mảnh `seq = 23` (Hex `0x0017` = 23).
* `00 33`: Tổng số mảnh `total = 51` (Hex `0x0033` = 51 mảnh).
* `05 78`: Độ dài dữ liệu `payload_len = 1400 bytes` (Hex `0x0578` = 1400).
* `f2 ff 13 a2`: Mã băm `CRC32` kiểm tra toàn vẹn của mảnh số 23.
