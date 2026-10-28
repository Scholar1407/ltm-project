# PROMPT CHO AGENT — Viết script benchmark hiệu năng giao thức SAP

## Bối cảnh

Bảng 4.4 "Đánh giá hiệu năng giao thức" hiện đang ghi khoảng ước lượng
(80-200ms, 350-600ms) KHÔNG có script/log nguồn — NotebookLM đã flag đây
là số liệu định tính giả danh định lượng. Cần số đo thật, tái lập được,
không cần 2 máy thật hay cài Clumsy (không đủ thời gian).

## Giải pháp: dùng lại FaultInjectingSocket đã có sẵn trong test suite

File `network/tests/test_reliability.py` đã có class fault-injection giả
lập mất gói tất định ở tầng socket. Tái sử dụng (import hoặc duplicate)
class này cho benchmark, KHÔNG viết lại từ đầu.

## Việc cần làm

Viết file `network/tests/benchmark_performance.py` (script độc lập, chạy
bằng `python -m network.tests.benchmark_performance`, KHÔNG phải pytest
test case — vì cần chạy nhiều trial và in report, không phải assert).

### Logic

1. Tạo 1 ảnh đại diện (dùng đúng kích thước ảnh JPEG thật mà hệ thống
   generate khi cảnh báo — khoảng 30-150KB, lấy 1 ảnh mẫu thật từ project
   nếu có, hoặc tạo synthetic cùng kích thước).
2. Với mỗi loss rate trong `[0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]`:
   - Chạy N=30 trial độc lập, mỗi trial dùng seed khác nhau cho
     FaultInjectingSocket để đảm bảo không thiên lệch 1 pattern mất gói
     cụ thể.
   - Mỗi trial: dùng in-process SmokeAlertSender + SmokeAlertReceiver qua
     loopback với socket bị inject loss, đo từ lúc gửi META đến lúc nhận
     ACK thành công (hoặc fail sau max_retries=5).
   - Ghi lại: tổng thời gian transfer (ms), số round NACK cần (0 = happy
     path không cần retransmit), thành công/thất bại.
3. Aggregate mỗi loss rate: mean latency, std dev latency, mean số round
   NACK, tỉ lệ thành công (%).

### Output

- CSV: `network/tests/benchmark_results.csv`, cột:
  `loss_rate, mean_latency_ms, std_latency_ms, mean_nack_rounds, success_rate_pct`
- In bảng Markdown sẵn dán vào Bảng 4.4:

```
| Tỉ lệ mất gói | Latency TB (ms) | Độ lệch chuẩn | Số round NACK TB | Tỉ lệ thành công |
|---|---|---|---|---|
| 0% | ... | ... | ... | 100% |
| 5% | ... | ... | ... | ...% |
| ... | | | | |
| 30% | ... | ... | ... | ...% |
```

### QUAN TRỌNG — ghi chú bắt buộc kèm số liệu

Số liệu đo bằng fault-injection harness **là overhead ở tầng giao thức
(thời gian chunking + chờ timeout + số round NACK), KHÔNG PHẢI round-trip
time thật trên mạng LAN vật lý** (vì chạy qua loopback trong 1 process,
không có network stack thật, không có RTT thật giữa 2 máy). Trong báo cáo,
Bảng 4.4 phải ghi rõ chú thích:

> *"Số liệu đo bằng benchmark_performance.py trên môi trường fault-injection
> tất định (loopback, in-process), phản ánh overhead của cơ chế reliability
> ở tầng giao thức SAP. Không đại diện cho độ trễ mạng LAN vật lý thật."*

**KHÔNG được ghi mập mờ như số đo LAN thật** — đây chính xác là loại lỗi
academic integrity giống vụ claim "+10-18%" không có bằng chứng ở Chương
2.3. Ghi đúng bản chất số liệu, dù nghe kém "ấn tượng" hơn số đo mạng thật.

### Nếu còn dư thời gian (optional, không bắt buộc)

Chạy thêm 1 lần test thật trên 2 máy qua LAN với Clumsy ở đúng 1 mức loss
(vd 15%) để sanity-check: thời gian thật có cùng bậc độ lớn (order of
magnitude) với số đo từ harness không. Chỉ cần 1 lần, không cần đủ 7 mức.
