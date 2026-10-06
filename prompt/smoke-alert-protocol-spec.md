# Smoke Alert Protocol (SAP) — Network Programming Course Project Spec

**Context:** Office Building Emergency Notification System, Network Programming course. Instructor wants demonstrable low-level socket/packet programming (TCP/UDP), not a web-API-style demo. A YOLO-based smoking detector (already trained — see companion spec) is the event trigger; this spec covers only the **network transmission layer**: sending a captured+timestamped frame from a sender machine to a receiver machine over LAN via a custom protocol on UDP.

**Stack:** Python, `socket` module (raw, no frameworks — this is the point of the course).

---

## 1. Design Rationale (do not deviate without reason)

- **UDP, not TCP.** TCP hides fragmentation/reliability inside the OS — nothing "low-level" to show. Building reliability manually on top of UDP (chunking, sequencing, NACK-based retransmission) is the actual learning objective and the most convincing proof this is a networking project, not an app demo.
- **Demo is split into three independent layers — do not merge them:**
  1. **Happy-path live demo**: real video → detect → send → receive → display. No fault injection anywhere in this path.
  2. **Resilience demo (announced, interactive)**: use an external, out-of-process tool to drop real packets at the network layer — never inside the application code. This keeps the reliability proof honest: the app does not know packets are being dropped and did not engineer its own test conditions.
  3. **Automated test**: a pytest suite with a mocked socket layer, deterministic, decoupled from any live network behavior — this is the artifact that proves correctness for grading, independent of whatever happens to occur on demo day.
- Fault injection tool for layer 2 (Windows): **Clumsy** — open-source, uses WinDivert to intercept and drop/lag/tamper live packets at the OS network layer, system-wide, requires zero code changes in the application, and works even on localhost. This is standard practice (same category as Linux's `tc netem`), not a hack — real packets are genuinely destroyed before reaching the socket.

## 2. Packet Format

```python
import struct

# Network byte order, no padding
HEADER_FORMAT = "!4sBIHHHI"
#                 magic(4s) type(B) img_id(I) seq(H) total(H) payload_len(H) crc32(I)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 19 bytes

MAGIC = b"SAP1"

class PacketType:
    META  = 1   # announces an incoming image transfer
    CHUNK = 2   # one fragment of image data
    ACK   = 3   # receiver confirms full image reassembled + CRC verified
    NACK  = 4   # receiver requests retransmission of specific seq numbers

MAX_PAYLOAD = 1400  # bytes; keeps full packet (19B header + payload) under
                     # typical 1472-byte safe UDP payload limit (Ethernet MTU 1500
                     # minus IP(20)+UDP(8) headers), avoiding IP-level fragmentation.
```

- `img_id` (4 bytes): unique per detected smoking event, lets the receiver distinguish concurrent/sequential transfers.
- `seq` / `total` (2 bytes each): chunk index and total chunk count — used for reassembly in the correct order regardless of UDP's unordered delivery.
- `crc32` (4 bytes): for `META` packets, this is the CRC32 of the *entire* reassembled image (used for final integrity check); for `CHUNK` packets, CRC32 of that chunk's payload only.

## 3. Sender State Machine

1. On smoking detection: capture frame, overlay timestamp, encode as JPEG.
2. Compute whole-image CRC32, split into `ceil(len(data) / MAX_PAYLOAD)` chunks.
3. Send one `META` packet: `img_id`, `total` chunk count, whole-image `crc32`.
4. Send all `CHUNK` packets in sequence (seq 0..total-1).
5. Enter a short wait window (e.g. 500ms) listening for `NACK`:
   - If `NACK` received with a list of missing seq numbers → resend only those chunks, reset the wait window.
   - If `ACK` received → transfer complete, log success, stop.
   - If wait window expires with no response (and max retry count, e.g. 5, is exhausted) → log failure, give up on this image (do not retry forever — the building isn't on fire because the network dropped a frame, don't let this block the next detection event).

## 4. Receiver State Machine

1. On `META`: allocate a reassembly buffer of `total` slots for this `img_id`, record expected CRC32, start an inactivity timer.
2. On `CHUNK`: verify the chunk's own CRC32 (log + silently drop if corrupted — it will be caught by the missing-chunk check below), store payload at `seq` index.
3. On inactivity timeout (e.g. 300ms since the last received chunk) with missing slots remaining: send one `NACK` listing missing seq numbers. Repeat up to a max retry count.
4. Once all slots filled: concatenate in order, verify whole-image CRC32 against the one from `META`.
   - Match → reconstruct image, send `ACK`, trigger UI notification (display image + timestamp).
   - Mismatch → treat as if chunks are still missing, re-send `NACK` for a full resend (rare edge case; corruption slipped past per-chunk CRC).

## 5. Logging Format (mandatory — this is what makes the demo visibly "networking")

Both sender and receiver print structured, human-readable logs for every packet event:
```
[SEND] META   img_id=4821 total=134 crc=0x9f2a1b00
[SEND] CHUNK  img_id=4821 seq=045/134 size=1400B crc=0x3fa2
[RECV] CHUNK  img_id=4821 seq=045/134 ✓
[RECV] NACK   img_id=4821 missing=[012,045] -> retransmitting
[RECV] ACK    img_id=4821 — transfer complete (134/134, 1 retransmit round)
```
Use consistent column alignment — readability during a live demo matters as much as correctness.

## 6. Resilience Demo Setup (Layer 2 — announced, external tool)

- Install Clumsy on the sender or receiver machine (or both).
- Demo script: "Happy path" run first with Clumsy off. Then explicitly state to the instructor that a network-degradation test follows, turn Clumsy on (e.g., 15-20% drop rate on UDP traffic for the relevant port), re-run, and narrate the `[DROP]` → `[NACK]` → retransmit → successful reassembly sequence as it appears in the logs.
- **Do not** add any Python-side random-drop code — the whole point is that the packet loss is real and external to the application under test.

## 7. Automated Test (Layer 3 — for correctness verification, not live demo)

Write `test_reliability.py` using `pytest`, with a thin wrapper around the sender/receiver sockets that deterministically drops a configured set of sequence numbers (e.g., seq 5 and seq 20 on the first send attempt only). Assert:
- The receiver's reassembled image byte-for-byte matches the original.
- Exactly one retransmission round occurred for the dropped sequence numbers.
- CRC32 check passes.

This test is independent of any live network condition and should pass deterministically every run — it is the evidence of correctness for the report/grading, separate from whatever happens live on demo day.

## 8. Repo Layout

```
ltm-project/
├── model/                          # DONE — do not modify. Final model: smoke_p2.
├── network/
│   ├── shared/protocol.py          # Section 2 — single source of truth, imported by both sides
│   ├── sender/
│   │   ├── sender.py                # Section 3
│   │   └── detector_bridge.py       # Section 9
│   ├── receiver/receiver.py        # Section 4
│   └── tests/test_reliability.py   # Section 7
├── ui/
│   ├── sender_ui.py
│   └── receiver_ui.py
└── prompt/
    ├── smoking-detection-spec.md
    └── smoke-alert-protocol-spec.md
```

## 9. `detector_bridge.py` — Detection-to-Network Bridge

**Final model (confirmed):** `model/weights/smoke_p2/best.pt` — YOLOv8s-P2, chosen over `smoke_baseline` per `MODEL_SELECTION_REPORT.md`. Load it once at startup, not per-frame.

```python
from ultralytics import YOLO

MODEL_PATH = "model/weights/smoke_p2/best.pt"
CONF_THRESHOLD = 0.5   # starting point — tune against clean_test_ids.txt results if too many false positives in the demo video
model = YOLO(MODEL_PATH)
```

**Critical design flaw to avoid — frame-rate alert flooding.** Do not wire detection directly to sending: a naive `if detection: send()` on every processed frame will fire **once per frame** for as long as the person keeps smoking. At 30fps, a 10-second smoking scene = ~300 duplicate `img_id`s, each triggering a full chunked UDP transfer — this floods both the network and the receiver's UI with hundreds of near-identical notifications for a single real-world event. This is exactly the kind of bug that doesn't show up in a quick manual test (you eyeball one notification and move on) but is obviously broken the moment anyone watches the receiver UI scroll uncontrollably during the demo.

**Fix — event-based triggering with cooldown, not frame-based:**
```python
import time

COOLDOWN_SECONDS = 8  # no new alert for the same ongoing event within this window
last_alert_time = 0

def on_frame_detection(frame, timestamp, confidence):
    global last_alert_time
    now = time.monotonic()
    if now - last_alert_time < COOLDOWN_SECONDS:
        return  # still inside the same smoking event — suppress duplicate alert
    last_alert_time = now
    # new event: capture, overlay timestamp, enqueue for sending (see below)
```
One detected smoking *event* (not every frame it's visible in) produces exactly one `img_id` and one transfer.

**Decouple detection from network I/O — use a queue, not a direct call.** The sender's retry/timeout logic (Section 3) can block for up to ~2.5s (5 retries × 500ms) in degraded-network conditions, especially during the Section 6 resilience demo with Clumsy active. If `detector_bridge.py` calls `sender.send()` synchronously inside the video-processing loop, a slow network retry stalls frame processing — the video appears to freeze for no visible reason, which looks like a bug, not a feature, during a demo. Use a producer-consumer pattern instead:
```python
import queue, threading

alert_queue = queue.Queue()

def sender_worker():
    while True:
        img_id, frame_bytes, timestamp = alert_queue.get()
        sender.send_image(img_id, frame_bytes, timestamp)  # Section 3 state machine runs here

threading.Thread(target=sender_worker, daemon=True).start()
```
`on_frame_detection` only pushes to `alert_queue` and returns immediately; video processing never waits on network state.

## 10. Deliverables Checklist for AntiGravity

- [ ] `network/shared/protocol.py` — packet struct pack/unpack helpers, `PacketType` enum, constants (Section 2)
- [ ] `network/sender/sender.py` — state machine per Section 3, structured logging per Section 5
- [ ] `network/sender/detector_bridge.py` — loads `model/weights/smoke_p2/best.pt`, event-based cooldown trigger, queue-decoupled send (Section 9)
- [ ] `network/receiver/receiver.py` — state machine per Section 4, structured logging per Section 5, triggers UI notification on successful `ACK`
- [ ] `network/tests/test_reliability.py` — deterministic pytest suite per Section 7
- [ ] `ui/sender_ui.py`, `ui/receiver_ui.py` — per repo layout, Section 8
- [ ] Demo runbook (markdown or slide notes): happy-path steps, then Clumsy-based resilience demo steps, narrating expected log output at each stage
