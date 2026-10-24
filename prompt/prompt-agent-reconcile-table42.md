# PROMPT CHO AGENT — Xác nhận dứt điểm số liệu aggregate trong Bảng 4.2

## Bối cảnh

Báo cáo hiện có Bảng 4.2 với các số liệu sau (đã điền sẵn, KHÔNG rõ nguồn):

| Chỉ số | Baseline | P2 |
|---|---|---|
| mAP50 (full test set) | 0.867 | 0.891 |
| mAP50-95 (full test set) | 0.541 | 0.572 |
| Recall (full test set) | 0.823 | 0.861 |
| Precision (full test set) | 0.879 | 0.892 |
| mAP50 (clean subset, 378 ảnh) | 0.854 | 0.903 |

Trong khi đó, lượt audit trước (đọc trực tiếp `results.csv` tại epoch tốt
nhất theo mAP50-95) cho ra số liệu KHÁC, đặc biệt lệch nhiều ở Recall và
mAP50-95 của P2:

| Chỉ số | Baseline (epoch 40) | P2 (epoch 41) |
|---|---|---|
| mAP50 | 0.87505 | 0.87862 |
| mAP50-95 | 0.53829 | 0.53748 |
| Recall | 0.81359 | 0.81073 |
| Precision | 0.85497 | 0.86386 |

**Nghi vấn:** `results.csv` log metric trên validation split MỖI EPOCH lúc
train — không phải test split thật. Số trong Bảng 4.2 hiện tại ghi rõ
"(full test set)" và "(clean subset, 378 ảnh)" — nếu đây là kết quả từ
một lần chạy `model.val()` riêng trên test split thật (không phải số từ
results.csv lúc train), thì ĐÂY MỚI LÀ SỐ ĐÚNG để dùng cho Chương 4, và
số từ results.csv (chỉ là val-split performance trong lúc train) không
nên dùng làm kết quả test chính thức.

## Việc cần làm

1. Tìm xem có file script nào tên gần giống `evaluate_models.py` trong
   `model/scripts/` (file-tree đã xác nhận có file này). Đọc nội dung
   script đó: nó chạy `model.val()` với `split=` gì (val/test), dùng
   data.yaml path nào, có augment/TTA không, conf/iou threshold bao nhiêu.
2. Chạy lại chính xác script đó (hoặc lệnh y hệt nếu không có script) cho
   CẢ HAI model, trên CẢ HAI tập: full test set (732 ảnh) và clean subset
   (378 ảnh, dùng `clean_test_ids.txt`).
3. Output: mAP50, mAP50-95, Recall, Precision cho từng model × từng tập
   — in rõ ràng, kèm **nguyên văn lệnh/command đã chạy** để có thể trích
   dẫn làm nguồn trong báo cáo (vd trong phụ lục hoặc footnote bảng).
4. So sánh kết quả mới chạy với bảng số đang có sẵn trong báo cáo
   (0.867/0.891/0.541/0.572/0.823/0.861/0.879/0.892/0.854/0.903) —
   xác nhận MATCH hay MISMATCH từng ô.
5. Nếu MISMATCH: báo rõ số nào đúng (dựa trên script/lệnh vừa chạy thật),
   KHÔNG tự đoán hay làm tròn để khớp số cũ.
6. Nếu không tìm thấy file `evaluate_models.py` hoặc không rõ cấu hình đã
   dùng để ra số liệu hiện tại trong báo cáo — báo rõ "không xác định
   được nguồn gốc số liệu cũ", kèm số liệu MỚI chạy được (có log, có
   command) để thay thế toàn bộ, không giữ lại số không rõ nguồn.

## QUAN TRỌNG

Số liệu Chương 4 "Kết quả thực nghiệm" của một đồ án PHẢI đến từ test
split chưa từng được model nhìn thấy trong lúc train — không được dùng số
validation-split log trong results.csv làm kết quả test chính thức, kể cả
khi 2 bộ số không lệch nhiều. Ưu tiên tuyệt đối: số nào có evidence trail
rõ ràng nhất (script + command + log output) thì dùng số đó, bất kể nó có
"đẹp" hơn hay không.
