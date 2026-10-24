# PROMPT CHO CODING AGENT — Xác thực số liệu & cấu trúc trong báo cáo

Bạn đang verify một báo cáo đồ án dựa trên source code thật tại
`d:\ASM2-scholar\Projects\ltm-project`. Nhiệm vụ của bạn KHÔNG phải sửa code,
mà **đọc code và trả về số liệu/cấu trúc THẬT**, sau đó đối chiếu với các
CLAIM dưới đây mà báo cáo đang khẳng định.

Với MỖI mục, hãy:
1. Mở đúng file được chỉ định.
2. Trích giá trị thật (copy nguyên văn constant/struct/class).
3. So sánh với CLAIM.
4. Kết luận MATCH / MISMATCH / KHÔNG TÌM THẤY.

Output bắt buộc là **một bảng Markdown duy nhất** theo format:

| # | Mục báo cáo | Claim | File:dòng kiểm tra | Giá trị thật trong code | Kết luận |
|---|---|---|---|---|---|

---

## A. Giao thức SAP (Chương 2.2 + Chương 3.5)

File chính: `network/shared/protocol.py` (nếu có `GIAI_THICH_GIAO_THUC_SAP.md`
ở root, đọc luôn — có thể là tài liệu gốc khi thiết kế, dùng làm nguồn đối chiếu
phụ, không phải nguồn chính).

1. Header format string chính xác là gì? (Claim: `"!4sBIHHHI"`, tổng 19 byte)
2. Thứ tự field trong header đúng là: magic(4s) → pkt_type(B) → img_id(I) →
   seq(H) → total(H) → payload_len(H) → crc32(I)? Verify từng field + kiểu dữ liệu.
3. Giá trị `MAX_PAYLOAD` đúng là bao nhiêu byte? (Claim: 1400)
4. Liệt kê TOÀN BỘ `PacketType` enum/constant trong file — đúng 6 loại
   (META=1, CHUNK=2, ACK=3, NACK=4, BEACON=5, PROBE=6) hay khác?
5. Cooldown chống flood cảnh báo — giá trị thật là bao nhiêu giây? (Claim: 8s)

## B. State machine Sender (Chương 2.2.5 + Chương 3.2)

File: `network/sender/sender.py`

6. Thời gian chờ ACK/NACK sau khi gửi hết chunk — bao nhiêu ms? (Claim: 500ms)
7. Số lần retry tối đa trước khi bỏ qua sự kiện — bao nhiêu? (Claim: 5)
8. Có đúng là 1 socket + 1 thread riêng cho mỗi receiver (fan-out concurrent)
   hay implementation thực tế khác (vd: dùng asyncio, hoặc single-thread loop)?
9. Hàng đợi giữa detection và network layer dùng `queue.Queue` chuẩn hay
   cấu trúc khác?

## C. State machine Receiver (Chương 2.2.6 + Chương 3.3)

File: `network/receiver/receiver.py`

10. Inactivity timer trước khi gửi NACK — bao nhiêu ms? (Claim: 300ms)
11. Thứ tự verify: CRC32 từng chunk trước, rồi CRC32 toàn ảnh sau khi đủ
    slot — đúng logic này không, hay code verify khác thứ tự?
12. Receiver có file `discovery.py` riêng không? **Lưu ý: file-tree hiện tại
    cho thấy `network/receiver/` CHỈ có `__init__.py`, `cli.py`, `receiver.py`
    — không có `discovery.py` riêng như bên sender.** Vậy logic BEACON
    broadcast (gửi mỗi 5s + reply PROBE) đang nằm ở đâu trong `receiver.py`?
    Trích class/function cụ thể.

## D. Auto-Discovery (Chương 2.2.8 + Chương 3.4)

File: `network/sender/discovery.py` + phần discovery trong `receiver.py` (câu 12)

13. Port discovery đúng là 5006, tách biệt với port data 5005? Verify cả
    2 phía sender và receiver dùng đúng port này.
14. Chu kỳ gửi BEACON (receiver) — bao nhiêu giây? (Claim: 5s)
15. Chu kỳ gửi PROBE (sender) — bao nhiêu giây? (Claim: 10s)
16. TTL của entry trong danh sách receiver đã khám phá — bao nhiêu giây?
    (Claim: 30s)

## E. Mô hình YOLOv8s-P2 (Chương 2.3 + Chương 4.1 — TRỌNG TÂM)

File: `model/weights/smoke_p2/results.csv`, `model/weights/smoke_p2/args.yaml`,
`model/weights/smoke_baseline/results.csv`, `model/weights/smoke_baseline/args.yaml`,
và `model/MODEL_SELECTION_REPORT.md`

17. Từ `results.csv` của **cả 2 model**, lấy giá trị tại epoch tốt nhất
    (epoch có mAP50-95 cao nhất, hoặc epoch cuối nếu dùng early stopping):
    - mAP50
    - mAP50-95
    - Precision
    - Recall
    Trả về rõ ràng cho CẢ HAI model, không làm tròn tùy tiện — lấy đúng số
    trong file.
18. Số epoch thực tế đã train là bao nhiêu (nhìn số dòng trong results.csv)?
    Có early-stop trước epoch 100 không?
19. Từ `args.yaml`: xác nhận `imgsz=640`, `batch`, `amp`, `patience`,
    `save_period` đúng như claim trong báo cáo hay khác.
20. Params và FLOPs: xác nhận 10.6M / 36.9 GFLOPs (P2) và 11.2M / 28.6
    GFLOPs (baseline) — các số này có log ở đâu trong quá trình train
    (thường ở đầu log hoặc trong model summary) hay cần tính lại bằng
    `model.info()`?

## F. Bộ kiểm thử Pytest (Chương 4.2.1)

File: `network/tests/test_reliability.py`

21. Liệt kê chính xác tên của TẤT CẢ test function trong file — có đúng
    11 test và đúng tên như báo cáo liệt kê không?
22. Chạy lại `pytest -v network/tests/test_reliability.py` và xác nhận
    kết quả hiện tại (có thể code đã đổi từ lần chạy trước, cần số liệu mới).

## G. Cấu trúc thư mục dự án (Bảng 3.1)

23. So sánh cây thư mục trong báo cáo (Bảng 3.1, nếu báo cáo có liệt kê)
    với thực tế từ `file-tree.md` người dùng cung cấp. Đặc biệt lưu ý các
    file MỚI chưa chắc đã được liệt kê trong báo cáo cũ:
    - `GIAI_THICH_GIAO_THUC_SAP.md` (file mới, root)
    - `pytest.ini` (file mới, root)
    - `model/scripts/evaluate_models.py`, `video_inference.py`,
      `prepare_sanity.py` (có được nhắc tên script nào trong Chương 4
      không, hay báo cáo dùng tên script khác?)

## H. Giao diện người dùng (Chương 3.6, Hình 3.3–3.5)

File: `ui/sender_ui.py`, `ui/receiver_ui.py`

24. Panel "Discovered Receivers" và nút "Probe Now" có thật sự tồn tại
    trong `sender_ui.py` như mô tả trong Chương 2.2.8 không?
25. Receiver UI có hiển thị rõ 2 trạng thái khác nhau (mặc định vs khi
    nhận cảnh báo) như Hình 3.3/3.4 mô tả — tìm đoạn code xử lý state
    này (callback/event handler nào trigger đổi UI).

---

**QUAN TRỌNG:** Nếu bất kỳ giá trị nào ở trên tìm thấy trong code KHÁC với
claim, đừng tự "làm tròn" để khớp — báo đúng số thật, kể cả khi nó lệch xa.
Nếu một field/class/constant không tồn tại ở vị trí được chỉ, tìm trong toàn
bộ `network/` và `ui/` trước khi kết luận "KHÔNG TÌM THẤY".
