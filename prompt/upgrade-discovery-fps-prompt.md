# Task for AntiGravity: Auto-discovery + Video FPS Fix

## Mandatory first step
Read these files before touching any code:
`network/shared/protocol.py`, `network/sender/sender.py`,
`network/sender/detector_bridge.py`, `ui/sender_ui.py`, `ui/receiver_ui.py`.
Report which acceptance criteria below are already satisfied. Only implement what is missing.
Do not rewrite code that already works correctly.

---

## Task A — Video FPS Fix

### Root cause (confirmed by code review)
`DetectorBridge.run_video_stream()` and `sender_ui.py` run `cap.read()` + YOLO inference +
frame annotation + UI render all on the **same thread**. YOLO inference alone costs 20-50ms/frame
on GPU; combined with tkinter Canvas redraw this causes the UI loop to fall behind the video's
native FPS, producing lag/skip/freeze.

### Required fix — producer-consumer frame pipeline

Split the video path into exactly **two threads**:

**Thread A — capture + inference (background, no UI calls):**
```python
while running:
    ret, frame = cap.read()
    if not ret:
        break
    annotated, detections = bridge.process_frame(frame)  # YOLO runs here
    try:
        frame_queue.put_nowait(annotated)   # drop old frame if queue full
    except queue.Full:
        try:
            frame_queue.get_nowait()        # evict stale frame
        except queue.Empty:
            pass
        frame_queue.put_nowait(annotated)
```

**Thread B — UI render (main thread or tkinter after_idle loop):**
```python
try:
    frame = frame_queue.get_nowait()
    # convert BGR→RGB, resize to canvas, update ImageTk
except queue.Empty:
    pass
root.after(16, render_loop)  # ~60Hz poll; adjust to match source FPS
```

Key constraints:
- Use `queue.Queue(maxsize=1)` — not a larger buffer. The UI always shows the **newest** frame,
  not a backlog. A larger queue just delays the freeze instead of fixing it.
- **Never call any tkinter widget method from Thread A.** Only `queue.put_nowait`.
- Thread A is a `daemon=True` thread; start it after `bridge.start()`.
- Thread A's loop must check a `threading.Event` stop flag (set by the Stop button / window close),
  not `self.running` alone — `self.running` is set by the bridge, not the UI.
- After Thread A exits, call `cap.release()` inside Thread A's finally block (not from the UI thread).
- The `on_frame_processed` callback in `DetectorBridge` is called from Thread A — it must only
  update shared state or push to a thread-safe queue; it must not touch tkinter directly.

Do **not** change `DetectorBridge.process_frame()` signature or behavior. The fix is entirely in
`ui/sender_ui.py` and the video loop wiring; `detector_bridge.py` internals stay the same unless
the existing UI already does this correctly (Step 0 check).

### Acceptance criteria — FPS
- [ ] A 30fps source video plays back at approximately its native FPS in the UI (measure with a
      simple frame counter / fps label in the UI — display current FPS as `FPS: XX` in the sender UI).
- [ ] YOLO inference detections and alert triggering still work correctly during playback.
- [ ] No tkinter "called from wrong thread" RuntimeError under any usage pattern.
- [ ] Stopping the stream (Stop button or window close) cleanly joins Thread A within 2 seconds.

---

## Task B — Auto-Discovery: Send to All Active Receivers on LAN

### Goal
The sender automatically finds every machine on the LAN that is running `receiver_ui.py` or
`network/receiver/cli.py`. No manual IP entry required (but keep the manual entry field as a
fallback/override). When an alert fires, it is delivered to **all discovered receivers** using the
existing multi-receiver fan-out in `sender.py` (do not change `sender.py`'s delivery logic).

### Protocol design — SAP Discovery (port 5006, separate from SAP data port 5005)

Add two new packet types to `protocol.py` (extend `PacketType`, do not change existing values or
the existing HEADER_FORMAT — the discovery packets use the same header struct for consistency):

```python
class PacketType:
    # existing
    META  = 1
    CHUNK = 2
    ACK   = 3
    NACK  = 4
    # new
    BEACON     = 5   # receiver → broadcast: "I am listening on port X"
    PROBE      = 6   # sender → broadcast: "Who is listening?"
```

BEACON packet layout (fields reused from existing header):
- `pkt_type = PacketType.BEACON`
- `img_id` = data port the receiver is listening on (e.g. 5005) — reuse `img_id` field (uint32)
- `seq = 0`, `total = 0`, `crc32 = 0`, `payload = b""`

PROBE packet layout:
- `pkt_type = PacketType.PROBE`
- all other fields = 0, `payload = b""`

Discovery port: **5006** (separate from SAP data port 5005 to avoid magic-header parse errors in
the existing receiver state machine).

### Receiver side changes

In `network/receiver/receiver.py` and `cli.py`: start a **DiscoveryBeaconThread** alongside the
existing receiver loop.

```python
class DiscoveryBeaconThread(threading.Thread):
    """
    Listens on UDP 5006 for PROBE packets and responds with BEACON.
    Also broadcasts BEACON on startup and every BEACON_INTERVAL seconds.
    """
    BEACON_INTERVAL = 5.0   # seconds between unsolicited beacons
    DISCOVERY_PORT  = 5006

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self.DISCOVERY_PORT))
        sock.settimeout(1.0)

        beacon_pkt = pack_packet(PacketType.BEACON, img_id=self.data_port,
                                 seq=0, total=0, crc32=0, payload=b"")

        # Startup beacon
        sock.sendto(beacon_pkt, ("<broadcast>", self.DISCOVERY_PORT))

        last_beacon = time.monotonic()
        while self._running:
            try:
                raw, addr = sock.recvfrom(256)
                pkt = unpack_packet(raw)
                if pkt.pkt_type == PacketType.PROBE:
                    sock.sendto(beacon_pkt, addr)  # unicast reply to sender
            except socket.timeout:
                pass
            if time.monotonic() - last_beacon >= self.BEACON_INTERVAL:
                sock.sendto(beacon_pkt, ("<broadcast>", self.DISCOVERY_PORT))
                last_beacon = time.monotonic()
```

The beacon must run as a **daemon thread** — it must not prevent the receiver from exiting.
Start it in `ReceiverNode.__init__` or equivalent, before the main receive loop.

### Sender side changes

Add a `DiscoveryListener` to `network/sender/` (new file `discovery.py`):

```python
class DiscoveryListener:
    """
    Discovers active SAP receivers on the LAN.
    Sends one PROBE on startup, then passively collects BEACON packets.
    Thread-safe: get_receivers() can be called from any thread.
    """
    DISCOVERY_PORT = 5006
    PEER_TTL       = 30.0   # remove peer if no beacon heard for this many seconds

    def probe(self): ...                          # send one PROBE broadcast
    def get_receivers(self) -> List[Tuple[str,int]]: ...  # thread-safe snapshot
    def start(self): ...                          # daemon thread
    def stop(self): ...
```

Implementation notes:
- Bind on `0.0.0.0:5006` with `SO_BROADCAST` and `SO_REUSEADDR`.
- Store peers as `{(host, data_port): last_seen_timestamp}` protected by a `threading.Lock`.
- `get_receivers()` returns peers whose `last_seen` is within `PEER_TTL` seconds — stale peers
  are silently excluded, no explicit removal needed.
- On BEACON received: update/insert `(addr[0], pkt.img_id)` — `img_id` carries the receiver's
  data port.
- Probe on startup, then every 10 seconds (re-probe to find newly-joined receivers).

### UI wiring in `sender_ui.py`

- On startup, create and start a `DiscoveryListener`; send an initial probe.
- Add a **"Discovered Receivers"** panel showing a live-updating list (refresh every 2 seconds
  via `root.after`): each entry shows `IP:port` and a green dot if seen within 10s / grey dot
  if stale. A "Probe Now" button sends an immediate PROBE broadcast.
- The manual `host:port` entry field stays. When an alert fires, merge:
  `receivers = discovery.get_receivers() + parse_endpoints(manual_field)` (deduplicated).
  If both are empty, show a warning in the UI and do not send (don't silently drop).
- On receiver_ui.py: show "Discovery: active (port 5006)" in the status bar.

### Windows firewall note (add to DEMO_RUNBOOK.md)
The discovery port 5006 also needs a firewall rule on the receiver machine:
```
netsh advfirewall firewall add rule name="SAP UDP 5006 Discovery" dir=in action=allow protocol=UDP localport=5006 profile=private
```

### Acceptance criteria — Auto-discovery
- [ ] Receiver running on Machine B appears in the sender UI's discovered list within 10 seconds
      of the receiver starting, with no manual IP entry.
- [ ] Killing the receiver and waiting >30s removes it from the discovered list.
- [ ] An alert fires to all currently-discovered receivers plus any manually-entered endpoints.
- [ ] Discovery traffic (port 5006) does not appear in, or interfere with, Wireshark captures
      filtered to `udp.port == 5005`.
- [ ] All existing pytest tests in `test_reliability.py` still pass.
- [ ] Add at least one pytest test: mock the UDP socket layer, assert that a PROBE sent by
      `DiscoveryListener` results in a discovered peer when a BEACON is received in reply.

---

## Out of scope
- mDNS/Zeroconf/Bonjour, any new pip dependencies, changes to `HEADER_FORMAT` or `MAX_PAYLOAD`,
  broadcast delivery of SAP data packets (discovery only; data delivery stays unicast per-receiver).

## Deliverables
- [ ] `network/sender/discovery.py` (new)
- [ ] `network/sender/sender.py` — unchanged (confirm in report)
- [ ] `network/shared/protocol.py` — add `BEACON`, `PROBE` to `PacketType`; add
      `PacketType.name()` entries for the new types
- [ ] `network/receiver/receiver.py` — add `DiscoveryBeaconThread`
- [ ] `network/receiver/cli.py` — start beacon thread
- [ ] `ui/sender_ui.py` — FPS fix (Task A) + discovery UI (Task B)
- [ ] `ui/receiver_ui.py` — show discovery status
- [ ] `DEMO_RUNBOOK.md` — add firewall rule for port 5006
- [ ] `network/tests/test_reliability.py` — add discovery probe/beacon test
- [ ] Report: list which Step 0 items were already satisfied vs. implemented now
