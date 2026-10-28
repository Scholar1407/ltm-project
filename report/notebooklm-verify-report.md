# BÁO CÁO KIỂM TOÁN TÍNH NHẤT QUÁN NỘI BỘ VÀ CHẤT LƯỢNG HỌC THUẬT
**Đồ án:** Hệ Thống Cảnh Báo Khói Tòa Nhà Qua Mạng UDP

---

## 1. Đánh số hình & bảng

| Loại | Chi tiết lỗi phát hiện | Vị trí / Chi tiết |
| :--- | :--- | :--- |
| **Bảng biểu** | **Không phát hiện lỗi** | Đánh số liên tục từ Bảng 2.1 đến Bảng 4.4, không trùng, không nhảy cóc. |
| **Hình ảnh** | **Trùng lặp số hình** | • **Hình 3.3** xuất hiện 2 lần: trang 24 ("Giao diện phía Sender") và trang 25 ("Giao diện phía Reciver mặc định").<br>• **Hình 4.7** xuất hiện 2 lần: trang 34 ("Chi tiết gói tin trong Wireshark") và trang 34 ("Giao diện sau khi khởi chạy receiver trên termux"). |
| **Hình ảnh** | **Nhảy cóc / Bỏ sót trong Danh mục** | Danh mục hình ảnh ở trang 4 bắt đầu trực tiếp từ **Hình 3.3**, hoàn toàn **bỏ sót Hình 3.1 và Hình 3.2**. |
| **Hình ảnh** | **Lỗi chính tả tiêu đề** | Ghi sai từ "Receiver" thành "Reciver" ở hai tiêu đề Hình 3.3 và Hình 3.4 trong danh mục. |

---

## 2. Đánh số mục/chương

| Mục kiểm tra | Kết quả audit | Chi tiết lỗi |
| :--- | :--- | :--- |
| **Số mục trùng / Nhầm tên** | **Có lỗi** | Trong thân bài Chương 5 (trang 38), mục 5.1 không được đánh số mục mà chỉ ghi tiêu đề là **"Kết luận"** (thiếu tiền tố "5.1."), sau đó liền kề mới đến **"5.2. Hạn chế"** và **"5.3. Kiến nghị..."**. |
| **Mục lục không khớp thân bài** | **Có lỗi** | Mục lục ghi "5.1. Kết luận", nhưng heading thực tế trong thân bài chỉ ghi "Kết luận". |
| **Trùng lặp cấu trúc mục** | **Có lỗi** | Cấu trúc tiêu đề các mục 1, 2, 3, 4 trong phần **MỞ ĐẦU** (trang 5) bị lặp lại tên nội dung với các mục 1.2.1, 1.2.2, 1.2.3, 1.3 trong **CHƯƠNG 1** (trang 7–9). |
| **Vi phạm quy tắc ≥2 tiểu mục** | **Cần lưu ý** | Mục **2.4 "Tổng quan về mạng LAN và truyền thông broadcast"** đứng độc lập và không có tiểu mục con (như 2.4.1, 2.4.2). |

---

## 3. Placeholder chưa điền

| Vị trí | Dạng placeholder phát hiện | Chi tiết nội dung chưa hoàn thiện |
| :--- | :--- | :--- |
| **Lời cam đoan (trang 3)** | Ký tự thiếu `"..."` | Cụm từ: *"dưới sự hướng dẫn của..."* chưa điền tên Giảng viên hướng dẫn (Thầy Nguyễn Văn Cẩn). |
| **Bảng 4.2 (trang 28)** | Ký tự `"-"` & thiếu số liệu | Chỉ số *"Recall object < 32px"* ở cột *"Chênh lệch"* chỉ ghi dấu gạch ngang **"-"** mà không có giá trị cụ thể. |
| **Bảng 2.4 & Bảng 4.2** | Chuỗi định tính thay số | Chỉ số *"Recall object < 32px"* ở cột *"YOLOv8s Baseline"* chỉ ghi chữ **"Baseline"** thay vì con số phần trăm cụ thể (ví dụ X%) để so sánh trực quan với chỉ số `+12.4%` của P2. |

---

## 4. Nhất quán thuật ngữ

| Thuật ngữ | Trạng thái nhất quán | Chi tiết đánh giá |
| :--- | :--- | :--- |
| **SAP / Smoke Alert Protocol** | **Nhất quán** | Được định nghĩa rõ là giao thức **tự thiết kế / tùy biến** ngay ở những lần xuất hiện đầu tiên tại Lời cam đoan ("Giao thức... do nhóm phát triển"), Danh mục viết tắt ("Giao thức mạng tùy biến được thiết kế trong đề tài này"), và Mục 1.2 ("Giao thức mạng UDP tùy biến SAP"). |
| **YOLOv8s-P2 vs YOLOv8-P2** | **Không nhất quán** | Tên mô hình bị gọi thiếu chữ 's' tại phần mở đầu Chương 4 (trang 27: ghi là **"YOLOv8-P2"**), trong khi toàn bộ các chương còn lại và Bảng 4.2 đều ghi chuẩn là **"YOLOv8s-P2"**. |
| **Port 5005 (data) & 5006 (discovery)** | **Lỗi kỹ thuật ở Mục 4.2.2** | Định nghĩa cổng ở Chương 2, 3 hoàn toàn chính xác (5005 cho dữ liệu ảnh, 5006 cho BEACON/PROBE). Tuy nhiên, tại **Mục 4.2.2 (trang 34)** ghi câu: *"Wireshark filter trên Laptop A: udp.port == 5005 → hiển thị rõ chuỗi gói META, CHUNK..., BEACON, PROBE"*. Đây là lỗi sai kiến thức mạng vì BEACON/PROBE chạy trên port 5006, bộ lọc `udp.port == 5005` sẽ không thể bắt được các gói discovery này. |

---

## 5. Mâu thuẫn số liệu nội bộ

| Mốc số liệu kiểm tra | Giá trị xuất hiện trong báo cáo | Đánh giá tính nhất quán |
| :--- | :--- | :--- |
| **11.10% small object** | Trang 27 (Bảng 4.1) & Trang 28 | **Nhất quán**: Bảng 4.1 ghi tỉ lệ tích lũy của nhóm *Rất nhỏ* (<16px: 1.67%) và *Nhỏ COCO* (16–32px: 9.43%) đúng bằng 1.67% + 9.43% = 11.10%. |
| **18.230 ảnh & 25.533 annotation** | Trang 19 (Mục 2.3.3) & Bảng 4.1 | **Nhất quán**: Tổng các tập Train (16.753) + Val (747) + Test (730) = 18.230 ảnh. Tổng các ô số lượng bounding box ở Bảng 4.1 đúng bằng 25.533. |
| **11 pytest PASSED** | Bảng 4.3, Mục 4.2.1 & Mục 5.1 | **Nhất quán**: Bảng 4.3 liệt kê đủ 11 test case, chạy kết quả 11/11 PASSED. |
| **Timeouts & Tham số mạng** | 500ms ACK, 300ms inactivity, cooldown 8s, TTL 30s, max retry 5 | **Nhất quán**: Các giá trị 500ms ACK timeout, 300ms inactivity timeout, 8s cooldown, 30s peer TTL, và 5 lần thử lại xuất hiện đồng nhất xuyên suốt các chương. |

---

## 6. Chất lượng học thuật — Chương 2.3 & Chương 3

| Tiêu chí | Nội dung kiểm tra | Đánh giá chi tiết |
| :--- | :--- | :--- |
| **Chương 2.3 (Chọn P2)** | **Chuỗi lập luận** | **Đầy đủ chuỗi lập luận**: Vấn đề (khó phát hiện vật thể nhỏ) → Bằng chứng số liệu (11.10% small object, 20.35% <32px) → Giải pháp kỹ thuật (thêm đầu P2 ở stride 4, feature map 160×160) → Đánh đổi (FLOPs tăng +29%). |
| **Chương 2.3 (Chọn P2)** | **Tuyên bố thiếu bằng chứng** | • Khẳng định đầu thuốc lá có *"kích thước điển hình 10×30 pixel"* (trang 18) mang tính ước lượng, không có trích dẫn/số liệu đo đạc cụ thể từ dataset.<br>• Bảng 2.4 ghi Recall baseline là chữ "Baseline" thiếu con số % mốc đối chứng. |
| **Chương 3 (Mô tả module)** | **Cách thức trình bày** | Trình bày theo hướng **liệt kê cấu trúc code và thông số hàm/lớp** (file `sender.py`, `receiver.py`, các hằng số, dataclass) hơn là phân tích kiến trúc phần mềm nâng cao. |
| **Chương 3 (Mô tả module)** | **Sơ đồ minh họa** | **Thiếu sơ đồ kiến trúc trọng yếu**: Không có Sơ đồ tuần tự (Sequence Diagram) thể hiện luồng bắt tay/truyền tin giữa Sender–Receiver và thiếu Sơ đồ lớp (Class Diagram) thể hiện mối quan hệ giữa các module. |

---

## 7. Chất lượng học thuật — Chương 4

| Tiêu chí | Nội dung kiểm tra | Đánh giá chi tiết |
| :--- | :--- | :--- |
| **Mục 4.3 (Hiệu năng)** | **Định lượng vs Định tính** | **Nghiêng về định tính & ước lượng khoảng rộng**: Bảng 4.4 đưa ra latency dạng khoảng ước lượng (80–200ms, 350–600ms). Thiếu các biểu đồ đo đạc phân bố latency/throughput theo tỉ lệ mất gói (loss rate từ 0% đến 30%), thiếu chỉ số độ lệch chuẩn (std dev) hay băng thông tức thời (Mbps). |
| **Mục 4.3 (Hiệu năng)** | **So sánh với TCP** | Chỉ nhận xét định tính dựa trên lý thuyết ("TCP cần N handshake..."), **không có thực nghiệm đối chứng** đo đạc trực tiếp giữa TCP và SAP trên cùng một môi trường mạng. |
| **Trùng lặp 4.4 & 5.1** | **Mức độ trùng lặp** | **Trùng lặp nội dung rất cao**: Mục 4.4 ("Đánh giá tổng quan") và Chương 5.1/5.2 ("Kết luận & Hạn chế") lặp lại gần như nguyên văn toàn bộ các ý về ưu điểm (giao thức SAP, CLI, Pytest, Zero-config, YOLOv8s-P2 mAP50) và hạn chế (không congestion control, không mã hóa, chỉ LAN IPv4). |
| **Nguồn gốc số liệu** | **Minh bạch nguồn dữ liệu** | Bảng 4.1 có nêu nguồn từ script `bbox_histogram.py`, Mục 4.2.1 nêu nguồn từ `pytest -v`. Tuy nhiên, **Bảng 4.4 (Hiệu năng SAP) không ghi rõ số liệu latency được trích xuất từ file log hay script benchmark nào**. |

---

## Top 5 vấn đề cần sửa trước khi nộp (xếp theo mức nghiêm trọng giảm dần)

1. **Lỗi logic cú pháp lọc Wireshark (Mục 4.2.2 - trang 34)**:
   - *Mô tả*: Văn bản hướng dẫn dùng bộ lọc `udp.port == 5005` để kiểm tra toàn bộ gói tin SAP (bao gồm BEACON và PROBE).
   - *Cách khắc phục*: Sửa bộ lọc thành `udp.port == 5005 || udp.port == 5006` vì gói discovery chạy trên cổng 5006.

2. **Lỗi đánh số Hình ảnh và Bỏ sót Danh mục (Chương 3, 4 & Danh mục)**:
   - *Mô tả*: Trùng số Hình 3.3 (trang 24, 25) và Hình 4.7 (trang 34); Danh mục Hình ảnh ở trang 4 bị nhảy cóc bỏ sót hoàn toàn Hình 3.1 và Hình 3.2.
   - *Cách khắc phục*: Đánh số lại toàn bộ hệ thống hình ảnh theo đúng thứ tự tăng dần và cập nhật lại Danh mục hình ảnh.

3. **Trùng lặp lớn nội dung giữa Mục 4.4 và Chương 5 (5.1 & 5.2)**:
   - *Mô tả*: Mục 4.4 và Chương 5 lặp lại nguyên văn các đánh giá ưu/nhược điểm, gây dư thừa văn bản.
   - *Cách khắc phục*: Viết lại Mục 4.4 tập trung vào việc thảo luận ý nghĩa kết quả thực nghiệm; dành Chương 5 cho việc tổng kết ngắn gọn mức độ đạt mục tiêu đồ án.

4. **Placeholder chưa hoàn thiện & Số liệu mốc Baseline (Lời cam đoan, Bảng 2.4 & 4.2)**:
   - *Mô tả*: Lời cam đoan còn ký tự `"..."` tại vị trí tên GVHD; Bảng 2.4 và 4.2 ghi chữ `"Baseline"` và dấu `"-"` ở chỉ số *Recall object < 32px*.
   - *Cách khắc phục*: Điền đầy đủ tên Thầy Nguyễn Văn Cẩn vào Lời cam đoan; bổ sung con số % cụ thể cho mốc Baseline (ví dụ: Baseline = 68.5%, P2 = 80.9%, Chênh lệch = +12.4%).

5. **Bổ sung Sơ đồ Kiến trúc (Chương 3) & Bổ sung nguồn số liệu Bảng 4.4 (Mục 4.3)**:
   - *Mô tả*: Chương 3 thiếu Sơ đồ tuần tự (Sequence Diagram) minh họa luồng truyền nhận SAP; Bảng 4.4 chưa nêu tên script/log file tạo ra số liệu thời gian truyền.
   - *Cách khắc phục*: Vẽ bổ sung 01 Sơ đồ tuần tự tương tác gói tin (META → CHUNK → NACK → ACK) ở Chương 3 và bổ sung ghi chú tên script benchmark/log file dưới chân Bảng 4.4.
