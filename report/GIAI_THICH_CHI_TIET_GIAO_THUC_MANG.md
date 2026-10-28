# BẢN HƯỚNG DẪN DỄ HIỂU VỀ GIAO THỨC SAP & CÁC KHÁI NIỆM MẠNG CỐT LÕI

> Tài liệu này được thiết kế như một **bài thuyết trình liền mạch**, xâu chuỗi các khái niệm kỹ thuật trong đề tài (Header, Payload, Struct format, Offset, MTU, CRC32, 6 loại gói tin) thành một câu chuyện thực tế dễ hiểu nhất.

---

## MỞ ĐẦU: BÀI TOÁN THỰC TẾ & Ý TƯỞNG CỦA HỆ THỐNG

Hãy tưởng tượng bạn đang xây dựng một hệ thống phát hiện hút thuốc trong tòa nhà:
1. Camera AI bắt được cảnh một người đang hút thuốc.
2. Hệ thống chụp lại một bức ảnh bằng chứng (dung lượng khoảng **40 KB – 60 KB**).
3. Hệ thống phải gửi bức ảnh này qua mạng LAN tới các màn hình bảo vệ ngay lập tức bằng giao thức **UDP** (để truyền siêu nhanh, không cần thủ tục bắt tay rườm rà như TCP).

**Nhưng rắc rối là:**
- Mạng máy tính không cho phép bạn ném một phát cả cục file 50 KB qua UDP.
- UDP lại là giao thức "gửi rồi mặc kệ", gói tin bay trên mạng có thể bị rơi rụng (packet loss) hoặc xáo trộn thứ tự.

👉 **Giải pháp:** Chúng ta phải tự thiết kế ra một quy tắc đóng gói riêng, đặt tên là **Giao thức SAP (Smoke Alert Protocol)**. Giao thức này sẽ:
- Cắt bức ảnh to thành nhiều mẩu nhỏ.
- Dán nhãn lên từng mẩu.
- Gửi đi và kiểm tra xem bên nhận có nhận đủ không, thiếu mẩu nào thì gửi lại đúng mẩu đó.

---

## PHẦN 1: GIẢI PHẪU 1 GÓI TIN — KHUNG VỎ (HEADER) VÀ RUỘT (PAYLOAD)

Mỗi một gói tin gửi qua mạng giống hệt như một **bưu kiện chuyển phát nhanh**:

```
┌──────────────────────────────────────────────────────────┐
│                    TOÀN BỘ GÓI TIN                       │
├──────────────────────────┬───────────────────────────────┤
│    PHẦN VỎ BƯU KIỆN      │        RUỘT BÊN TRONG         │
│   (HEADER: Cố định 19B)  │  (PAYLOAD: 0 đến 1400 Bytes)  │
│  [Mã nhận diện, Số thứ tự,│  [Mẩu ảnh thật cắt nhỏ, hoặc  │
│   Tổng số gói, Mã CRC32] │   danh sách gói thiếu...]     │
└──────────────────────────┴───────────────────────────────┘
```

### 1. Header 19 bytes là gì? Sao có gói 19 bytes, có gói tận 14xx bytes?

- **Header (19 bytes):** Là **chiếc phong bì thư chuẩn hóa**. Trên chiếc phong bì này, ta ghi các thông tin quản lý: *Đây là gói tin loại gì? Của bức ảnh nào? Mẩu thứ mấy? Tổng cộng bao nhiêu mẩu?* 
  - Chiếc phong bì này **luôn luôn cố định đúng 19 bytes**, không thừa không thiếu một hạt bụi nào!
- **Payload (Dữ liệu ruột):** Là **nội dung chứa bên trong phong bì**.
  - Có những gói chở theo một mẩu ảnh nặng **1400 bytes**. Khi đó: **19B (vỏ) + 1400B (ruột) = 1419 bytes**.
  - Nhưng có những gói tin chỉ đóng vai trò "báo tin" (như gói **ACK** báo *"Tôi nhận xong rồi"* hay gói **BEACON** báo *"Tôi đang online"*). Những gói này **không cần chở mẩu ảnh nào cả** (Payload = 0 bytes). Vì vậy toàn bộ gói tin **chỉ dài đúng 19 bytes** của phần Header!

---

### 2. Chuỗi ký tự kỳ lạ `!4sBIHHHI` nghĩa là gì?

Khi lập trình bằng Python, máy tính không hiểu được các khái niệm như "chữ cái", "con số" trừu tượng, mà nó chỉ hiểu các dãy byte nhị phân `0` và `1`. 

Để xếp các thông tin quản lý vào đúng 19 bytes của Header, ta dùng hàm `struct.pack()` của Python với định dạng **`!4sBIHHHI`**. Đây chính là **bản thiết kế (blueprint)** quy định thứ tự và kích thước từng ô trên chiếc phong bì:  

| Ký tự | Tên trường | Ý nghĩa thực tế | Kích thước |
| :---: | :--- | :--- | :---: |
| `!` | Network byte order | Quy ước chuẩn quốc tế của mạng Internet (Big-Endian: byte lớn đứng trước). | *(Chỉ thị)* |
| `4s` | `magic` | 4 ký tự cố định: `"SAP1"`. Đóng vai trò như con dấu niêm phong nhận diện riêng của đồ án. | **4 bytes** |
| `B` | `pkt_type` | Loại gói tin (từ số 1 đến số 6). `B` là số nguyên dương nhỏ (1 byte, 0–255). | **1 byte** |
| `I` | `img_id` | Mã định danh sự kiện/bức ảnh. `I` là số nguyên 4 bytes (0 đến 4 tỷ). | **4 bytes** |
| `H` | `seq` | Số thứ tự của mẩu này (0, 1, 2, ...). `H` là số nguyên 2 bytes (0–65.535). | **2 bytes** |
| `H` | `total` | Tổng số mẩu mà bức ảnh này bị cắt ra. | **2 bytes** |
| `H` | `payload_len` | Độ dài thật của phần ruột đi kèm trong gói này. | **2 bytes** |
| `I` | `crc32` | Mã kiểm tra chống hỏng dữ liệu của gói này. | **4 bytes** |
| **Tổng cộng** | | **4 + 1 + 4 + 2 + 2 + 2 + 4 = 19 bytes** | **19 bytes** |

---

### 3. MTU là gì? Tại sao ta chỉ cắt ruột tối đa 1400 bytes (`MAX_PAYLOAD = 1400`)?

- **MTU (Maximum Transmission Unit):** Là **"kích thước tối đa của một thùng hàng"** mà hạ tầng mạng vật lý (dây mạng LAN, router Wi-Fi) cho phép vận chuyển trong một chuyến.
  - Chuẩn mạng Ethernet phổ biến trên toàn cầu có **MTU = 1500 bytes**. Nếu bạn gửi một gói tin vượt quá 1500 bytes, router mạng sẽ buộc phải băm nhỏ gói tin ra ở tầng IP (hiện tượng IP Fragmentation), rất dễ gây nghẽn mạng và mất gói tin.
- **Tính toán an toàn trong đồ án:**
  Khi gói tin của chúng ta di chuyển trên mạng, nó sẽ được bọc thêm các lớp vỏ của hệ điều hành:
  > **1400B (Ruột ảnh) + 19B (Header SAP) + 8B (Header UDP) + 20B (Header IPv4) = 1447 bytes**

  Con số **1447 bytes < 1500 bytes (MTU)**. Nhờ vậy, gói tin đi thẳng qua mọi card mạng và router một cách mượt mà nhất, không bao giờ bị phân mảnh ở tầng dưới!

---

## PHẦN 2: TỌA ĐỘ VÀ KIỂM TRA CHẤT LƯỢNG (OFFSET & CRC32)

### 4. Offset là gì?

**Offset** hiểu đơn giản là **"khoảng cách tính từ vạch xuất phát"** (vị trí lệch bao nhiêu bước/bao nhiêu byte tính từ điểm đầu tiên).

Trong đề tài này, từ "Offset" xuất hiện ở 2 ngữ cảnh:

#### Ngữ cảnh 1: Offset trong bức ảnh (Khi cắt file)
Giả sử bức ảnh dài 40.000 bytes:
- Mẩu số 0 lấy từ byte 0 đến 1399 (Offset = 0).
- Mẩu số 1 lấy từ byte 1400 đến 2799 (**Offset = 1400**).
- Bên nhận khi ghép ảnh lại, chỉ cần dựa vào số thứ tự để biết đặt mẩu này vào **Offset** nào trong bộ nhớ để ghép thành bức tranh hoàn chỉnh.

#### Ngữ cảnh 2: Offset trong Wireshark (Vị trí 42)
Khi phần mềm Wireshark bắt một gói tin trên đường dây mạng, gói tin đó gồm nhiều lớp bọc vào nhau như búp bê Nga:
1. Lớp Ethernet Header: dài **14 bytes** (từ byte 0 đến byte 13).
2. Lớp IPv4 Header: dài **20 bytes** (từ byte 14 đến byte 33).
3. Lớp UDP Header: dài **8 bytes** (từ byte 34 đến byte 41).
4. **Và bắt đầu từ byte thứ 42 trở đi**: Chính là nơi giao thức SAP của chúng ta bắt đầu xuất hiện!

> **14 (Ethernet) + 20 (IP) + 8 (UDP) = 42 bytes**

👉 Vì vậy, khi mentor nói *"Magic bytes SAP1 nằm ở Offset 42"*, nghĩa là nếu bạn đếm từ đầu gói tin Ethernet lùi vào **42 bước (offset 42)**, bạn sẽ thấy ngay 4 chữ cái `53 41 50 31` (tức chữ `"SAP1"` trong bảng mã ASCII).

---

### 5. CRC32 là gì và nó làm cái gì?

**CRC32 (Cyclic Redundancy Check 32-bit)** là một thuật toán toán học giúp **tạo ra một "dấu vân tay" gồm 4 bytes (32-bit)** đại diện cho một khối dữ liệu.

- **Nó hoạt động như thế nào?**
  Trước khi gửi một mẩu ảnh, Sender tính toán dữ liệu của mẩu đó và ra được một con số, ví dụ `0xA1B2C3D4`, rồi ghi con số này vào Header.
  Khi Receiver nhận được mẩu ảnh, nó cũng tự chạy lại thuật toán trên mẩu ảnh vừa nhận:
  - Nếu kết quả tính ra **trùng khớp** `0xA1B2C3D4` → Mẩu ảnh nguyên vẹn 100%, không bị nhiễu sóng làm biến dạng bit nào.
  - Nếu tính ra khác con số trên → Dữ liệu trên đường truyền đã bị méo mó, Receiver lập tức **vứt bỏ mẩu đó vào sọt rác** để tránh ghép ảnh bị lỗi!

- **Cơ chế kiểm tra 2 lớp của đề tài:**
  1. **Lớp 1 (Kiểm tra từng mẩu - Chunk CRC):** Mỗi mẩu CHUNK có mã CRC riêng để bảo vệ chính nó.
  2. **Lớp 2 (Kiểm tra toàn bộ bức ảnh - Whole-Image CRC):** Gói META thông báo mã CRC của toàn bộ file ảnh 50KB. Sau khi Receiver gom đủ tất cả các mẩu, nó kiểm tra CRC một lần cuối cùng trên toàn bộ bức ảnh đã ghép trước khi hiện lên màn hình cảnh báo.

---

## PHẦN 3: 6 LOẠI GÓI TIN — 6 NHÂN VẬT TRONG VỞ KỊCH TRUYỀN TIN

Giao thức SAP định nghĩa đúng **6 loại gói tin** (đánh số từ 1 đến 6 trong trường `pkt_type`). Chúng được chia thành 3 nhóm nhiệm vụ rõ ràng:

```
                  ┌───────────────────────────────────────────────┐
                  │          6 LOẠI GÓI TIN TRONG SAP             │
                  └───────────────────────┬───────────────────────┘
                                          │
       ┌──────────────────────────────────┼──────────────────────────────────┐
       ▼                                  ▼                                  ▼
 [NHÓM TRUYỀN DỮ LIỆU]            [NHÓM SỬA LỖI & BÁO TIN]         [NHÓM TỰ ĐỘNG TÌM NHAU]
  1. META   (Báo xuất hàng)        3. ACK   (Báo nhận đủ)           5. BEACON (Loa phát thanh)
  2. CHUNK  (Thùng chở hàng)       4. NACK  (Báo đòi hàng thiếu)     6. PROBE  (Hỏi tìm kiếm)
```

---

### Nhóm 1: Truyền dữ liệu ảnh (Sender → Receiver)

#### 1. Gói META (`pkt_type = 1`) — "Bản hóa đơn xuất hàng"
- **Để làm gì:** Gửi đi đầu tiên trước khi gửi ảnh để báo cho Receiver chuẩn bị tinh thần.
- **Nó nói gì:** *"Này Receiver, tôi chuẩn bị gửi bức ảnh mã số `#101`. Bức ảnh này bị cắt ra làm tổng cộng `30 mẩu`. Mã CRC của toàn bộ ảnh khi ghép xong phải là `0xABCD1234` đấy nhé!"*
- **Kích thước:** Thường chỉ dài **19 bytes** (hoặc thêm vài chục bytes chuỗi ngày giờ phát hiện khói).

#### 2. Gói CHUNK (`pkt_type = 2`) — "Thùng hàng chở mẩu ảnh"
- **Để làm gì:** Chở từng mẩu dữ liệu nhị phân của bức ảnh.
- **Nó nói gì:** *"Tôi là mẩu thứ `5` trong tổng số `30 mẩu` của bức ảnh `#101`. Đây là `1400 bytes` ruột của tôi."*
- **Kích thước:** Nặng nhất trong hệ thống, thường dài khoảng **1419 bytes** (19 bytes Header + 1400 bytes ruột ảnh).

---

### Nhóm 2: Báo nhận và sửa lỗi (Receiver → Sender)

#### 3. Gói NACK (`pkt_type = 4`) — "Giấy báo đòi hàng thiếu"
- **Để làm gì:** Khi Receiver nhận được các mẩu ảnh nhưng thấy bị lủng (ví dụ nhận được mẩu 1, 2, 4 nhưng mất mẩu 3), sau 300ms im ắng không thấy gói nào bay tới nữa, Receiver sẽ gửi NACK về cho Sender.
- **Nó nói gì:** *"Tôi nhận được ảnh `#101` rồi nhưng bị rơi mất mẩu `[003, 015]`. Gửi lại gấp đúng 2 mẩu này cho tôi!"*
- **Kích thước:** 19 bytes Header + danh sách các số nguyên 2 bytes chỉ vị trí gói bị thiếu.

#### 4. Gói ACK (`pkt_type = 3`) — "Biên lai giao hàng thành công"
- **Để làm gì:** Khi Receiver đã gom đủ 30/30 mẩu và kiểm tra mã CRC toàn ảnh thấy trùng khớp 100%, nó gửi ACK về để Sender kết thúc phiên làm việc.
- **Nó nói gì:** *"Tôi đã nhận trọn vẹn bức ảnh `#101`, ảnh rất nét, CRC hoàn toàn khớp. Sender được phép nghỉ ngơi!"*
- **Kích thước:** Dài đúng **19 bytes** (chỉ có Header báo tin, Payload = 0).

---

### Nhóm 3: Tự động khám phá không cần cấu hình IP (Auto-Discovery qua Port 5006)

#### 5. Gói BEACON (`pkt_type = 5`) — "Tiếng chuông điểm danh định kỳ"
- **Để làm gì:** Màn hình Receiver khi bật lên cứ mỗi **5 giây** sẽ tự động phát một gói BEACON ra toàn mạng LAN (Broadcast).
- **Nó nói gì:** *"Alo mọi người ơi, tôi là Trạm Bảo Vệ, tôi đang online tại cổng 5005 để chờ nhận cảnh báo khói nhé!"*
- **Kích thước:** Dài đúng **19 bytes** (Payload = 0).

#### 6. Gói PROBE (`pkt_type = 6`) — "Lời dò hỏi của Trạm phát"
- **Để làm gì:** Khi máy Sender (Camera AI) bật lên, nó không biết trạm bảo vệ đang ở địa chỉ IP nào. Nó phát một gói PROBE ra toàn mạng để quét tìm.
- **Nó nói gì:** *"Có trạm nhận nào trong mạng LAN đang bật không? Lên tiếng giùm tôi!"*
- Khi trạm Receiver nghe thấy tiếng hỏi này, nó sẽ lập tức đáp lại bằng một gói BEACON để Sender tự động lưu IP vào danh sách gửi tin mà không cần con người phải ngồi gõ IP bằng tay.
- **Kích thước:** Dài đúng **19 bytes** (Payload = 0).

---

## PHẦN 4: TOÀN BỘ KỊCH BẢN KHI PHÁT HIỆN HÚT THUỐC DIỄN RA NHƯ THẾ NÀO?

Hãy theo dõi một chu trình khép kín từ lúc phát hiện khói đến khi màn hình bảo vệ hú còi:

```
    MÁY CAMERA AI (SENDER)                            MÁY BẢO VỆ (RECEIVER)
              │                                                │
   [1] Cắt ảnh thành 40 mẩu                                    │
              │                                                │
              │────── 1. Gói META (Báo có 40 mẩu ảnh) ────────>│ (Receiver mở sổ theo dõi #101)
              │                                                │
              │────── 2. Gói CHUNK (Mẩu 0 đến 39) ────────────>│ (Gói số 5 & 20 bị rớt mạng!)
              │                                                │
              │                                                │ (Đợi 300ms thấy thiếu gói 5 & 20)
              │<───── 3. Gói NACK (Báo thiếu mẩu 5 và 20) ─────│ 
              │                                                │
   [2] Lục kho gửi lại mẩu 5 & 20                              │
              │────── 4. Gói CHUNK (Gửi lại mẩu 5 & 20) ──────>│ 
              │                                                │ (Đủ 40 mẩu! Tính CRC32 toàn ảnh -> OK)
              │                                                │ [Hiển thị ảnh báo động đỏ 🚨]
              │<───── 5. Gói ACK (Đã nhận trọn vẹn ảnh) ───────│ 
              │                                                │
   [3] Hoàn tất phiên gửi!                                     │
```

---

## TỔNG KẾT BẰNG BẢNG NHANH CHO BẠN TRẢ LỜI VẤN ĐÁP

| Khái niệm | Giải thích ngắn gọn nhất (Điểm cốt lõi) |
| :--- | :--- |
| **Header 19B** | Chiếc phong bì quản lý cố định (luôn chiếm 19 bytes đầu tiên của mọi gói tin SAP). |
| **Payload** | Phần ruột chứa hàng (có thể chứa 1400B mẩu ảnh, hoặc 0 bytes đối với gói báo tin). |
| **`!4sBIHHHI`** | Bản vẽ kỹ thuật quy định 7 ngăn trên chiếc phong bì 19 bytes theo chuẩn mạng Big-Endian. |
| **Offset** | Tọa độ lệch tính từ vạch xuất phát (vị trí cắt ảnh, hoặc vị trí byte 42 trong Wireshark). |
| **MTU** | Thùng hàng tối đa của mạng (1500B). Ta chọn ruột 1400B để tổng gói luôn ≤ 1447B < 1500B. |
| **CRC32** | Con dấu kiểm tra toàn vẹn 4 bytes để phát hiện và vứt bỏ gói tin bị hỏng bit do nhiễu mạng. |
| **6 loại gói tin** | `META` (hóa đơn), `CHUNK` (hàng hóa), `ACK` (đã nhận đủ), `NACK` (đòi hàng thiếu), `BEACON` (điểm danh online), `PROBE` (quét tìm trạm). |
