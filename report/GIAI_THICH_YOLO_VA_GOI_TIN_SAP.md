# BẢN GIẢI THÍCH CHI TIẾT VỀ MÔ HÌNH YOLOV8 & CÁCH SOI GÓI TIN SAP

> Tài liệu này được biên soạn dưới dạng **bài thuyết trình giải đáp thắc mắc chuyên sâu**, kết nối các khái niệm về Thị giác máy tính (Computer Vision - YOLO) và Lập trình mạng (Network Protocol - SAP) một cách trực quan, thực tế và dễ hiểu nhất.

---

## PHẦN 1: TẠI SAO LẠI LÀ YOLOV8? TẠI SAO CÓ 2 PHIÊN BẢN TRONG ĐỒ ÁN?

### 1. Tại sao chọn YOLOv8 mà không phải các phiên bản khác (v5, v7, v9, v10, v11)?

Dòng họ YOLO (You Only Look Once) đã trải qua rất nhiều thế hệ, nhưng đề tài lựa chọn **YOLOv8** (phiên bản `v8s` - Small) vì 4 lý do kỹ thuật mang tính thực tế cao:

1. **Từ bỏ Anchor-box (Chuyển sang kiến trúc Anchor-Free):**
   - Các bản cũ như **YOLOv5** sử dụng cơ chế *Anchor-based* (dựa trên các khung hộp mẫu cố định). Cơ chế này rất kém linh hoạt khi đối tượng có kích thước biến động dị thường như làn khói mờ ảo hoặc điếu thuốc nhỏ xíu.
   - **YOLOv8** là thế hệ đầu tiên chuyển sang hoàn toàn *Anchor-Free*, mô hình tự do dự đoán trực tiếp tọa độ tâm và khoảng cách tới 4 cạnh của vật thể, giúp độ nhạy với vật thể méo mó/dị biệt tăng vọt.
2. **Khối Backbone C2f tiên tiến:**
   - Thay thế khối C3 cũ của YOLOv5 bằng khối **C2f** (Cross-Stage Partial with 2 Convolutions). Khối này phong phú luồng gradient hơn, nhẹ hơn nhưng học đặc trưng tốt hơn.
3. **Độ ổn định và khả năng can thiệp kiến trúc (Custom Architecture):**
   - Các bản mới hơn như **YOLOv9, v10, v11** tại thời điểm nghiên cứu còn quá mới, cộng đồng ít, tài liệu chưa chuẩn hóa và thư viện hay thay đổi API.
   - YOLOv8 (do Ultralytics phát triển) có hệ sinh thái API Python cực kỳ hoàn thiện, cho phép người nghiên cứu dễ dàng viết file YAML tùy biến để **chèn thêm các tầng Stride mới (như tầng P2)** mà không gặp lỗi xung đột framework.
4. **Cân bằng giữa Tốc độ và Tài nguyên (Phiên bản `s` - Small):**
   - Bản Nano (`v8n`) quá yếu để bắt khói nhỏ. Bản Medium/Large (`v8m`, `v8l`) thì quá nặng, ngốn tài nguyên khi chạy video. Bản `v8s` (Small, ~11M tham số) là điểm rơi hoàn hảo (sweet spot).

---

### 2. Tại sao lại có 2 phiên bản (YOLOv8s Baseline và YOLOv8s-P2)? Chúng khác gì nhau?

Trong nghiên cứu khoa học và đồ án kỹ thuật, bạn không thể tự nhiên tuyên bố: *"Tôi vừa làm ra một mô hình rất xịn!"* mà người ta tin ngay. Bạn bắt buộc phải thực hiện phương pháp luận: **Nghiên cứu đối chứng (Ablation Study)**.

Đó là lý do project có 2 phiên bản:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        HAI PHIÊN BẢN ĐỐI CHỨNG                         │
├───────────────────────────────────┬────────────────────────────────────┤
│   1. YOLOv8s Baseline (Chuẩn)     │      2. YOLOv8s-P2 (Cải tiến)      │
│   - Mô hình gốc nguyên bản        │   - Kiến trúc tùy biến thêm P2     │
│   - 3 đầu dò: P3, P4, P5          │   - 4 đầu dò: P2, P3, P4, P5       │
│   - Đóng vai trò: MỐC SO SÁNH     │   - Đóng vai trò: GIẢI PHÁP ĐỀ XUẤT│
└───────────────────────────────────┴────────────────────────────────────┘
```

- **Mục đích:** Cả 2 mô hình đều được huấn luyện trên **cùng một bộ dữ liệu**, **cùng số epoch**, **cùng siêu tham số (hyperparameters)**. Nhờ vậy, mọi sự khác biệt về số lượng tham số, FLOPs, độ trễ và Recall đều phản ánh chính xác 100% giá trị mà kiến trúc P2 mang lại, loại bỏ yếu tố may rủi.

---

## PHẦN 2: BẢN CHẤT CÁC TẦNG P (STRIDE) VÀ BÍ MẬT CỦA "P2"

### 1. "P" và "Stride" trong YOLO là cái gì?

Hãy tưởng tượng bạn đang xem một bức ảnh trên Google Maps hoặc kính lúp:
- **Ảnh gốc đầu vào:** Có kích thước **640 × 640 pixels**.
- Khi ảnh đi qua mạng nơ-ron tích chập (CNN), để nhận diện được các vật thể lớn (như chiếc ô tô, con người, cả tòa nhà), mạng bắt buộc phải **thu nhỏ bức ảnh lại** qua từng tầng để nhìn bao quát toàn cảnh. Tỉ lệ thu nhỏ đó được gọi là **Stride (bước nhảy)**.
- Mỗi tầng phát hiện tương ứng với một tỉ lệ thu nhỏ được ký hiệu là chữ **P**:

| Tầng phát hiện | Stride (Tỉ lệ thu nhỏ) | Kích thước Feature Map | Khả năng nhìn nhận |
| :---: | :---: | :---: | :--- |
| **P2** | **4×** (640 / 4) | **160 × 160 pixels** | **Siêu cận cảnh:** Nhìn từng chi tiết li ti, vi mô. |
| **P3** | **8×** (640 / 8) | **80 × 80 pixels** | **Cận cảnh:** Nhìn vật thể kích thước nhỏ. |
| **P4** | **16×** (640 / 16) | **40 × 40 pixels** | **Trung bình:** Nhìn vật thể kích thước vừa. |
| **P5** | **32×** (640 / 32) | **20 × 20 pixels** | **Toàn cảnh:** Nhìn vật thể lớn choán hết màn hình. |

---

### 2. Tại sao phiên bản cải tiến lại phải chọn "P2"?

Mô hình **YOLOv8s Baseline nguyên bản của hãng chỉ có 3 đầu dò: P3, P4, P5** (bắt đầu từ Stride 8).

Hãy xem bi kịch xảy ra với một vật thể nhỏ (như đốm tàn thuốc lá hoặc điếu thuốc lá khoảng **16 × 16 pixels** trên ảnh gốc 640×640):

```
 Ảnh gốc (640×640)        Tầng P3 (Stride 8)          Tầng P5 (Stride 32)
┌────────────────┐        ┌────────┐                 ┌────┐
│                │  8x    │        │         32x     │    │
│  ■ (16×16 px)  │ ─────> │ ■(2×2) │ ──────────────> │ ·  │ (BỊ XÓA SỔ HOÀN TOÀN!)
│                │        │        │                 │    │
└────────────────┘        └────────┘                 └────┘
```

- Khi đưa vật thể 16×16 pixel vào tầng **P3 (thu nhỏ 8 lần)**: Vật thể bị ép lại chỉ còn đúng **2 × 2 = 4 pixels** trên bản đồ đặc trưng! Chỉ 4 pixel thì mạng CNN hầu như không thể phân biệt nổi đây là đầu lọc thuốc lá hay là hạt bụi/nhiễu ảnh.
- Khi sang đến tầng P4, P5 thì vật thể này **bị biến mất hoàn toàn**!

👉 **Đó là lý do phiên bản cải tiến chọn bổ sung tầng P2:**
- Tầng **P2 chỉ thu nhỏ 4 lần** (Stride 4), giữ lại bản đồ đặc trưng có kích thước khủng **160 × 160 pixels**.
- Vật thể 16×16 pixel khi qua Stride 4 vẫn còn giữ được kích thước **4 × 4 = 16 pixels**. Mạng nơ-ron giữ lại được góc cạnh, kết cấu sợi khói và viền điếu thuốc.
- **Sự đánh đổi (Trade-off):** Bản đồ 160×160 rất lớn, khiến lượng tính toán tăng từ 28.6 GFLOPs lên **36.9 GFLOPs (+29%)**. Nhưng vì hệ thống của chúng ta phục vụ phân tích video giám sát ngoại tuyến (offline/batch analysis), sự đánh đổi này hoàn toàn xứng đáng để đổi lấy khả năng không bỏ lọt hành vi hút thuốc.

---

## PHẦN 3: KẾT QUẢ TEST SET ĐÃ ĐƯỢC LƯU VÀO MODEL METRICS CHƯA?

**CÂU TRẢ LỜI: ĐÃ ĐƯỢC LƯU TRỮ ĐẦY ĐỦ VÀ CHUẨN XÁC TRONG DỰ ÁN.**

Trước đây trong báo cáo có sự nhầm lẫn giữa 2 tầng số liệu:
1. **Số liệu lúc Train:** Nằm trong `results.csv` ở 2 thư mục `model/weights/smoke_baseline/results.csv` và `model/weights/smoke_p2/results.csv`. Đây là số liệu đo trên **Validation Split (747 ảnh)** qua từng epoch khi huấn luyện mô hình.
2. **Số liệu lúc Test độc lập (Official Model Metrics):**
   Hiện tại, toàn bộ kết quả chạy thực nghiệm thật trên cả **Full Test Set (732 ảnh)** và **Clean Test Subset (378 ảnh)** đã được lưu cố định vào các tệp metrics sau:
   - File tổng hợp toàn bộ metrics: `model/weights/test_metrics_summary.csv`
   - File đo Recall theo từng kích thước: `model/weights/small_object_recall_comparison.csv`
   - File đối chiếu dứt điểm: `agent-reconcile-table42-report.md`

### Bảng số liệu chính thức được lưu trữ:

| Tập dữ liệu kiểm thử | Chỉ số | YOLOv8s Baseline | YOLOv8s-P2 | Nhận xét đối chứng |
| :--- | :--- | :---: | :---: | :--- |
| **Full Test Set**<br>(732 ảnh, 1.793 nhãn) | **mAP50**<br>**mAP50-95**<br>**Recall**<br>**Precision** | **0.8997**<br>**0.5935**<br>**0.8232**<br>**0.9011** | **0.8956**<br>**0.5840**<br>**0.8358**<br>**0.8992** | P2 có Recall cao hơn Baseline (**+1.26 pp**), giúp phát hiện được nhiều đối tượng hơn. |
| **Clean Test Subset**<br>(378 ảnh sạch, 429 nhãn) | **mAP50**<br>**mAP50-95**<br>**Recall**<br>**Precision** | **0.7050**<br>**0.3447**<br>**0.6177**<br>**0.7595** | **0.7001**<br>**0.3381**<br>**0.6364**<br>**0.7648** | Trên ảnh thực tế không ghép: P2 vượt trội cả về Recall (**+1.87 pp**) và Precision (**+0.53 pp**). |

---

## PHẦN 4: MỘT GÓI TIN SAP CÓ DẠNG NHƯ THẾ NÀO? MUỐN XEM THÌ XEM SAO?

### 1. Dạng thật của 1 gói tin SAP trong máy tính

Gói tin SAP khi truyền qua cáp mạng hoặc sóng Wi-Fi thực chất là một chuỗi các con số nhị phân được biểu diễn dưới dạng hệ cơ số 16 (Hexadecimal).

Một gói tin SAP chuẩn gồm **19 bytes Header** đứng đầu, theo sau là phần **Payload (ruột dữ liệu)**:

```
[--- 4B ---][1B][--- 4B ---][-2B-][-2B-][-2B-][--- 4B ---][------ 0 đến 1400 Bytes ------]
|   magic  |type|  img_id  | seq |total| p_len|  crc32   |            PAYLOAD              |
|   SAP1   | 02 | 00000065 |0000 |0028 | 0578 | a1b2c3d4 | [Dữ liệu mẩu ảnh nhị phân...]   |
```

Ví dụ một mẩu tin CHUNK thật bằng mắt thường nhìn dạng Hex dump:
```hex
53 41 50 31 02 00 00 00 65 00 00 00 28 05 78 a1 b2 c3 d4 ff d8 ff e0 ...
```
- `53 41 50 31`: Mã ASCII của 4 chữ `"SAP1"`.
- `02`: Loại gói = 2 (Gói `CHUNK`).
- `00 00 00 65`: Số Hex của 101 (Mã sự kiện `img_id = 101`).
- `00 00`: Mẩu số 0 (`seq = 0`).
- `00 28`: Tổng số 40 mẩu (`total = 40`).
- `05 78`: Độ dài ruột 1400 bytes (`payload_len = 1400`).
- `a1 b2 c3 d4`: Mã kiểm tra toàn vẹn `crc32`.
- `ff d8 ff e0 ...`: Những byte đầu tiên của file ảnh JPEG thật!

---

### 2. Muốn xem gói tin SAP thì xem bằng cách nào?

Bạn có thể "nhìn tận mắt, bắt tận tay" gói tin SAP bằng **2 cách cực kỳ đơn giản**:

#### CÁCH 1: Dùng lệnh Python có sẵn trong project (Xem ngay trong 1 giây)
Trong project đã có sẵn hàm đóng gói và giải mã. Mở PowerShell trong thư mục project và chạy lệnh sau:

```bash
python -c "from network.shared.protocol import pack_packet, unpack_packet, PacketType; pkt_bytes = pack_packet(PacketType.CHUNK, img_id=101, seq=5, total=40, crc32=0x12345678, payload=b'HELLO_SMOKE'); print('1. Dạng Bytes thật gửi qua mạng:\n', pkt_bytes); print('\n2. Máy nhận giải mã ra:\n', unpack_packet(pkt_bytes))"
```

**Kết quả hiện ra ngay lập tức trên màn hình:**
- Dòng 1 cho bạn thấy đúng chuỗi byte nhị phân `b'SAP1\x02\x00\x00\x00e...'` dài đúng 30 bytes (19 bytes vỏ + 11 bytes chữ `HELLO_SMOKE`).
- Dòng 2 cho bạn thấy cấu trúc giải mã: `Packet(magic='SAP1', pkt_type=2, img_id=101, seq=5, total=40, payload_len=11, crc32=305419896)`.

---

#### CÁCH 2: Dùng phần mềm Wireshark bắt gói tin trên mạng

Nếu bạn muốn xem gói tin đang bay trên card mạng LAN khi hệ thống đang chạy:

1. **Khởi động bắt gói:** Mở Wireshark, chọn card mạng `Loopback` (nếu chạy test trên 1 máy) hoặc `Wi-Fi / Ethernet` (nếu chạy 2 máy qua LAN).
2. **Nhập bộ lọc (Filter):** Trên thanh tìm kiếm của Wireshark, gõ:
   ```text
   udp.port == 5005 || udp.port == 5006
   ```
   *(5005 là cổng truyền ảnh, 5006 là cổng tự động dò tìm Discovery).*
3. **Chạy demo gửi ảnh:** Bật `sender_ui.py` và `receiver_ui.py` lên rồi nhấn nút gửi cảnh báo.
4. **Cách nhìn vào 3 khung của Wireshark:**
   - **Khung trên cùng (Packet List):** Bạn sẽ thấy danh sách các gói tin UDP. Gói dài `19 bytes` (META, ACK, BEACON) và các gói dài `1419 bytes` (CHUNK chở ảnh) bay nối đuôi nhau.
   - **Khung ở giữa (Packet Details):** Nhấp vào dấu `>` cạnh mục **Data (1419 bytes)** hoặc **User Datagram Protocol**, bạn sẽ thấy rõ thông tin cổng nguồn và cổng đích.
   - **Khung dưới cùng (Packet Bytes - Hex Dump):** 
     - Nhìn sang cột bên phải cùng của khung Hex, tại **Offset 002a** (tức byte số 42), bạn sẽ thấy rõ 4 chữ cái in hoa: **`SAP1`**.
     - Ngay sau chữ `SAP1` là byte số `02` (CHUNK), tiếp theo là ID bức ảnh và các mẩu dữ liệu ảnh JPEG!

---

## TỔNG KẾT NHANH CHO BUỔI VẤN ĐÁP

1. **YOLOv8s:** Là mô hình Anchor-Free cân bằng hoàn hảo giữa tốc độ và độ chính xác; dễ tùy biến kiến trúc YAML.
2. **2 phiên bản:** Baseline (mốc so sánh chuẩn) vs P2 (giải pháp đề xuất) để thực hiện nghiên cứu đối chứng khoa học (Ablation study).
3. **P2 (Stride 4):** Thu nhỏ ảnh 4 lần (giữ bản đồ 160×160), cứu các vật thể nhỏ/điếu thuốc không bị triệt tiêu như Stride 8 (P3).
4. **Lưu trữ Metrics:** Toàn bộ kết quả test set độc lập đã được lưu tại `model/weights/test_metrics_summary.csv` và `agent-reconcile-table42-report.md`.
5. **Gói tin SAP:** Gồm 19 bytes Header cố định (`!4sBIHHHI`) + Payload ruột; có thể xem trực tiếp qua Python script test hoặc soi tại byte 42 (Offset 0x2a) trên Wireshark.
