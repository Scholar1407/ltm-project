# 🚬 Smoke Alert System — Tòa Nhà Thông Minh
### Phát Hiện Hành Vi Hút Thuốc & Cảnh Báo Khẩn Cấp Qua Giao Thức Mạng Tùy Biến (Smoke Alert Protocol - SAP)

**Học phần:** Lập trình mạng (Network Programming)  
**Công nghệ chính:** Python, Raw UDP Sockets, YOLOv8s-P2, Tkinter Dark-Mode UI.

---

## 📌 1. Giới Thiệu Dự Án

Hệ thống kết hợp giữa **Thị giác máy tính (Computer Vision)** và **Lập trình mạng mức thấp (Transport Layer / UDP Sockets)** nhằm phát hiện người hút thuốc trong khuôn viên tòa nhà và phát tín hiệu báo động kèm ảnh chụp hiện trường đến **toàn bộ các trạm giám sát trong mạng LAN**:

```
[Camera / Video Stream]
         │
         ▼
[YOLOv8s-P2 AI Engine] ──(Event Cooldown: 8s)
         │
         ▼
[Producer-Consumer Queue] ──(Tách biệt luồng, video giữ vững 30 FPS)
         │
         ▼
[SmokeAlertSender] ──(Auto-Discovery UDP 5006)──► [Toàn bộ Receiver trong LAN]
         │
         ├─► [Receiver 1 (Laptop B): UDP 5005]  ──► Báo động đỏ + Ảnh chụp hiện trường
         ├─► [Receiver 2 (Phone Termux): UDP 5005] ──► Bắn thông báo Android Notification
         └─► [Receiver N (Server/Headless): UDP 5005] ──► Tự động lưu ảnh vào disk
```

---

## 💡 2. Các Điểm Sáng Kỹ Thuật (Key Highlights)

1. **Giao thức tùy biến Smoke Alert Protocol (SAP):**
   - Xây dựng trực tiếp trên **Raw UDP Sockets** (không dùng TCP).
   - Tự động chia nhỏ ảnh JPEG thành các phân mảnh `CHUNK <= 1400B` tránh phân mảnh tầng IP.
   - Cơ chế tin cậy **Selective-NACK ARQ**: Khi mạng rớt gói, chỉ truyền lại đúng các phân mảnh bị mất.
   - Kiểm tra toàn vẹn 2 lớp bằng mã băm **CRC32** (từng chunk và toàn bộ bức ảnh).

2. **Tự động dò tìm mạng LAN (Zero-Configuration Auto-Discovery):**
   - Hoạt động trên cổng phụ **UDP 5006** tách biệt với luồng dữ liệu 5005.
   - Cơ chế phát `PROBE` và phản hồi `BEACON`: Sender tự động phát hiện tất cả các Receiver đang online mà **không cần nhập địa chỉ IP thủ công**.
   - Cơ chế **Multi-Receiver Fan-out**: Phân phối song song cảnh báo tới mọi máy nhận (1 socket + 1 worker độc lập cho từng máy, không nghẽn nhau).

3. **Kiến trúc luồng Decoupled Video Pipeline (30 FPS Mượt Mà):**
   - Tách rời luồng xử lý AI (Thread A) và luồng hiển thị giao diện Tkinter (Thread B) qua hàng đợi `maxsize=1`.
   - Video camera/file luôn hiển thị mượt mà ở tốc độ thực (`FPS: ~30`), triệt tiêu hoàn toàn hiện tượng khựng/lag/treo giao diện.

4. **Trọng số AI tối ưu vật thể nhỏ (YOLOv8s-P2):**
   - Bổ sung đầu phát hiện P2 (stride-4) chuyên biệt cho việc bắt đầu thuốc lá kích thước nhỏ ($< 32 \times 32$ px) ở góc quay camera xa.
   - Trọng số đã huấn luyện sẵn lưu tại `model/weights/smoke_p2/best.pt`.

---

## 📁 3. Cấu Trúc Thư Mục Dự Án

```
ltm-project/
├── model/
│   └── weights/smoke_p2/best.pt     # Trọng số mô hình YOLOv8s-P2 đã huấn luyện
├── network/
│   ├── shared/
│   │   └── protocol.py              # Định nghĩa header 19-byte, packet types (META, CHUNK, ACK, NACK, BEACON, PROBE)
│   ├── sender/
│   │   ├── sender.py                # Core UDP Sender (Multi-receiver fan-out, Selective-NACK)
│   │   ├── discovery.py             # DiscoveryListener (quét & thu thập receiver trên LAN cổng 5006)
│   │   └── detector_bridge.py       # Cầu nối YOLO AI, Cooldown 8s, Queue phân tách luồng
│   ├── receiver/
│   │   ├── receiver.py              # Core UDP Receiver (Reassembly session, NACK generator, DiscoveryBeaconThread)
│   │   └── cli.py                   # Headless Receiver (dành cho Server, VM, Android Termux)
│   └── tests/
│       └── test_reliability.py      # Bộ 11 ca kiểm thử tự động (pytest)
├── ui/
│   ├── sender_ui.py                 # Giao diện Trạm Gửi (Webcam/Video, YOLO overlay, FPS counter, Packet Log)
│   └── receiver_ui.py               # Giao diện Trạm Nhận (Báo động đỏ khẩn cấp, Xem ảnh, Packet Log)
├── DEMO_RUNBOOK.md                  # Hướng dẫn chi tiết các kịch bản demo và vấn đáp
└── requirements.txt                 # Danh sách thư viện phụ thuộc
```

---

## ⚡ 4. Cài Đặt Nhanh (Quick Start)

### Bước 1: Kích hoạt môi trường và cài đặt thư viện
```powershell
# 1. Tạo và kích hoạt môi trường ảo
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Cài đặt thư viện
pip install -r requirements.txt
```
*(Nếu có card đồ họa NVIDIA RTX: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124`)*.

### Bước 2: Chạy ứng dụng
- **Tại Trạm Nhận (Receiver):**
  ```powershell
  python ui/receiver_ui.py
  ```
- **Tại Trạm Gửi (Sender / Camera):**
  ```powershell
  python ui/sender_ui.py
  ```

### Bước 3: Chạy kiểm thử tự động (Pytest)
```powershell
pytest -v network/tests/test_reliability.py
```

👉 Xem kịch bản thực nghiệm chi tiết (mô phỏng rớt gói mạng Clumsy, kết nối điện thoại Android Termux, câu hỏi vấn đáp) tại [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).
