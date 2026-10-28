# 🚬 Hướng Dẫn Thực Nghiệm & Báo Cáo Demo (SAP Runbook Tinh Gọn)
**Đề tài:** Hệ thống Cảnh Báo Hút Thuốc qua Giao Thức Mạng Tùy Biến (Smoke Alert Protocol - SAP)  
**Tính năng nổi bật:** Tự động dò tìm (Auto-Discovery) & Gửi cảnh báo đến TẤT CẢ trạm nhận trong LAN.

---

## 🚀 1. Cách Hệ Thống Tự Động Gửi Đến Toàn Bộ Thiết Bị Trong LAN

Hệ thống hoạt động theo cơ chế **Zero-Configuration (Không cần nhập IP thủ công)**:

1. **Trạm Nhận (Receiver - Port 5006 & 5005):**
   - Khi bật `receiver_ui.py` hoặc `cli.py`, máy nhận tự động mở cổng **UDP 5006** (Discovery) và phát sóng gói tin `BEACON` báo danh trên toàn mạng LAN.
2. **Trạm Gửi (Sender - Camera/Webcam):**
   - Khi bật `sender_ui.py`, Sender phát sóng `PROBE` (UDP 5006) để quét toàn bộ mạng LAN.
   - Mọi máy Receiver đang bật trong mạng LAN sẽ lập tức tự động xuất hiện tại danh sách **Discovered Receivers** với chấm xanh `🟢`.
3. **Phát Cảnh Báo Đồng Thời (Building-wide Fan-out):**
   - Khi phát hiện khói hoặc bấm nút **"🚨 Trigger Alert Frame"**, Sender **tự động phân phối song song** ảnh cảnh báo đến **TẤT CẢ** các máy Receiver đã tìm thấy trong LAN cùng lúc (mỗi máy nhận 1 worker + 1 socket UDP độc lập, không nghẽn nhau).

---

## 🛠️ 2. Chuẩn Bị & Cài Đặt Môi Trường Từ Đầu (A to Z)

Thực hiện các bước sau trên Laptop (chỉ cần làm 1 lần duy nhất):

### Bước 2.1: Tạo và kích hoạt môi trường ảo Python
Mở Terminal (PowerShell) tại thư mục dự án `ltm-project`:
```powershell
# 1. Tạo môi trường ảo
python -m venv .venv

# 2. Kích hoạt môi trường ảo (PowerShell):
.venv\Scripts\Activate.ps1
```
*(Nếu PowerShell báo lỗi bảo mật chặn script, chạy: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` rồi chạy lại lệnh kích hoạt).*  
*(Nếu dùng Command Prompt thông thường: chạy `.venv\Scripts\activate.bat`)*.

### Bước 2.2: Cài đặt thư viện phụ thuộc (requirements.txt)
```powershell
# Cài đặt đầy đủ các gói cần thiết: ultralytics, opencv, pillow, pytest,...
pip install -r requirements.txt
```
*(Tùy chọn tăng tốc: Nếu laptop có card đồ họa rời NVIDIA RTX, bạn có thể cài thêm bản PyTorch CUDA để chạy mô hình AI mượt mà nhất: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124`)*.

### Bước 2.3: Mở cổng Firewall trên Windows (Bắt buộc cho Receiver)
Mở PowerShell bằng quyền **Administrator** và chạy 2 lệnh sau:
```powershell
# Mở cổng nhận dữ liệu ảnh cảnh báo (Port 5005)
netsh advfirewall firewall add rule name="SAP UDP 5005 Data" dir=in action=allow protocol=UDP localport=5005 profile=private

# Mở cổng tự động dò tìm trạm nhận (Port 5006)
netsh advfirewall firewall add rule name="SAP UDP 5006 Discovery" dir=in action=allow protocol=UDP localport=5006 profile=private
```

### Bước 2.4: Kết nối chung mạng LAN
Đảm bảo các laptop/thiết bị kết nối cùng một mạng Wi-Fi (hoặc phát Wi-Fi Hotspot từ điện thoại di động).

---

## 🎬 3. Kịch Bản Thực Hiện Demo (3 Bước Chính)

### Bước 1: Khởi động các trạm nhận (Laptop B, C,... trong LAN)
Trên từng máy nhận:
```powershell
python ui/receiver_ui.py
```
- Màn hình hiển thị banner xanh: `🟢 ALL ZONES SECURED — LISTENING FOR ALERTS`.
- Góc phải thông báo: `📡 Discovery: active (port 5006)`.

#### Dành cho Android (Termux):
Nếu trên điện thoại đang lưu bản `network` cũ (chưa có cổng Discovery 5006), hãy xóa và cập nhật bản mới:
1. **Trên Laptop:** Bật web server chia sẻ file nhanh:
   ```powershell
   python -m http.server 8000
   ```
2. **Trên Termux:** Xóa code cũ, tải `network.zip` mới và giải nén (thay `<IP_LAPTOP>` bằng IP Wi-Fi laptop, vd: `10.234.204.156`):
   ```bash
   # Xóa bản cũ
   rm -rf network network.zip
   
   # Tải bản mới và giải nén
   curl -O http://<IP_LAPTOP>:8000/network.zip && unzip -o network.zip
   ```
   Giải nén xong thì tắt terminal đi đc rồi.

3. **Khởi chạy Receiver trên Termux:**
   ```bash
   python -m network.receiver.cli --bind 0.0.0.0 --port 5005 --out received/ --notify-cmd "termux-notification --title '🚨 CẢNH BÁO HÚT THUỐC' --content 'Phát hiện sự kiện #{img_id}' --image-path '{path}' --action 'termux-open {path}'"
   ```
   *(Màn hình Termux sẽ báo: `SAP Auto-Discovery beacon active on UDP port 5006`)*.

---

### Bước 2: Khởi động trạm gửi (Laptop A - laptop ném video vào)
Trên máy gửi:
```powershell
python ui/sender_ui.py
```
- **Quan sát panel "Discovered Receivers":** Sender tự quét mạng LAN và hiện danh sách tất cả các trạm nhận đang online kèm chấm xanh `🟢 IP:5005 (seen 0.Xs ago)`.
- **Không cần nhập IP thủ công** (ô *Manual Endpoints* có thể để trống hoặc dùng làm địa chỉ dự phòng).
- Bấm **"🔍 Probe Now"** nếu muốn cưỡng bức quét lại ngay lập tức.

---

### Bước 3: Phát cảnh báo đến toàn bộ mạng LAN
1. Nhấn **▶ Start Stream** (Webcam hoặc Video) để YOLOv8s-P2 nhận diện tự động (với tốc độ hiển thị mượt mà đạt chuẩn `FPS: 30`), HOẶC nhấn ngay nút **🚨 Trigger Alert Frame**.
2. **Hiện tượng quan sát được:**
   - **Tại Sender:** Gói tin `META` và các `CHUNK` được gửi đồng thời tới **toàn bộ các địa chỉ IP** trong danh sách LAN.
   - **Tại TẤT CẢ các máy Receiver:** Cùng lúc chuyển sang nhấp nháy đỏ báo động: `🚨 CRITICAL ALERT: SMOKE DETECTED IN BUILDING!`.
   - Ảnh chụp hiện trường sắc nét bung lên đồng loạt trên tất cả các màn hình, xác thực toàn vẹn `CRC32 Check: PASSED ✓`.

---

## 🛡️ 4. Demo Độ Tin Cậy Khi Mạng Mất Gói (Clumsy) & Kiểm Thử Tự Động

### A. Demo mất gói với Clumsy (Thuyết minh tính bền vững UDP)
1. Mở `clumsy.exe` (Run as Administrator) trên máy Sender.
2. Filter: `udp and (udp.DstPort == 5005 or udp.SrcPort == 5005)`.
3. Ô Presets không cần chọn gì cả.
4. Bật **Drop 15% - 20%** -> Nhấn **Start**.
5. Bấm **🚨 Trigger Alert Frame**:
   - Nhìn vào cột Log: Receiver phát hiện thiếu chunk -> gửi gói **NACK** với danh sách `missing=[...]`.
   - Sender chỉ gửi lại đúng các chunk bị thiếu (**Selective Retransmit**), không gửi lại toàn bộ.
   - Sau 1 hiệp truyền lại, ảnh hiển thị trọn vẹn 100%, không bị vỡ hay rách ảnh.

### B. Kiểm thử tự động (11/11 Tests Passed)
Chạy bộ test tự động kiểm tra trọn vẹn logic giao thức, dung lỗi node chết, và cơ chế discovery:
```powershell
pytest -v network/tests/test_reliability.py
```
*(Đạt 11/11 tests PASSED: kiểm thử mất gói, hỏng CRC, multi-receiver, dead node tolerance, discovery PROBE/BEACON mock).*

---

## 💡 5. Tóm Tắt Ý Chính Trả Lời Vấn Đáp

1. **Tại sao tự làm trên UDP thay vì dùng TCP?**
   - Để làm chủ kiến thức tầng giao vận: tự phân mảnh gói `<= 1400B` tránh phân mảnh IP, tự đánh số `seq/total`, kiểm tra toàn vẹn 2 lớp `CRC32`, cơ chế Selective-NACK ARQ và Auto-Discovery độc lập.
2. **Làm sao truyền đồng thời cho nhiều máy trong LAN?**
   - Sender sử dụng Discovery (cổng 5006) tìm ra danh sách IP. Khi có sự kiện khói, Sender tạo luồng worker và socket riêng cho từng máy nhận để truyền song song (N-unicast fan-out), một máy bị lag hay mất mạng không làm ảnh hưởng đến các máy còn lại.
3. **Cơ chế chống nghẽn và giật lag hình ảnh?**
   - **Video Pipeline 2 luồng:** Tách riêng luồng xử lý AI (Thread A) và luồng vẽ giao diện Tkinter (Thread B) qua hàng đợi `maxsize=1`, giúp camera luôn giữ mức 30 FPS mượt mà.
   - **Event Cooldown 8s:** Ngăn chặn việc gửi dồn dập hàng trăm cảnh báo trong một lần phát hiện người hút thuốc.
