# Task for AntiGravity: Upgrade SAP project from single-machine to real two-laptop LAN demo

## Context
The project (`ltm-project`) already works with sender and receiver as two terminals on one machine. The final demo will run on **two separate laptops on the same LAN** (sender laptop with the model, receiver laptop as the management station). Do not change the SAP wire format (`network/shared/protocol.py` header, packet types, MAX_PAYLOAD). All existing pytest tests must keep passing.

**Step 0 (mandatory, before editing anything):** read `network/sender/sender.py`, `network/sender/detector_bridge.py`, `network/receiver/receiver.py`, `ui/sender_ui.py`, `ui/receiver_ui.py`, and `DEMO_RUNBOOK.md`. Report which of the items below are already satisfied (e.g. host/port already configurable) and only implement what is missing. Do not rewrite working code.

## Task 1: Configurable network endpoints (no hardcoded 127.0.0.1)
- Receiver binds to `0.0.0.0` by default (configurable bind host and port, default port 5005). A receiver bound to `127.0.0.1` cannot be reached from another laptop.
- Sender takes a list of receiver endpoints (`host:port`). Provide it via (a) CLI argument(s) and (b) an input field in `sender_ui.py`. Default may stay `127.0.0.1:5005` for single-machine testing.
- On startup, receiver prints its bound address and all local IPv4 addresses (so the user can read the LAN IP without opening `ipconfig`). Use `socket` only, no new dependencies.
- Validate host/port input and show a clear error in the UI, not a stack trace.

## Task 2: Multiple receivers (building-wide notification)
- When an alert fires, the sender delivers the **same image** to **every** configured receiver.
- Design constraint: **one UDP socket per receiver, one worker per receiver**. Each worker runs the existing Section 3 sender state machine independently against its own socket. This keeps ACK/NACK demultiplexing trivial (replies arrive on that receiver's own socket) and ensures one dead or slow receiver never blocks delivery to the others.
- The existing cooldown and producer-consumer queue stay as they are: one detection event = one `img_id`, fanned out to N receivers.
- Logs must identify the peer: `[SEND] CHUNK -> 192.168.1.20:5005 img_id=... seq=...`. Keep the existing column alignment.
- Receiver logs must show the sender address: `[RECV] CHUNK <- 192.168.1.10:51234 ...`. Receiver reassembly state must be keyed by `(sender_addr, img_id)`, not `img_id` alone.
- Add a pytest test: two receivers, deterministic loss on one of them, assert both end up with a byte-identical image and that only the lossy one performed a retransmit round.

## Task 3: Patch `DEMO_RUNBOOK.md`
Keep the existing structure and Vietnamese language. Make these changes:
1. Fix the confusing section title "Tổng Quan Kiến Trúc 3 Tầng": the ASCII diagram is the **data-flow architecture**; the three "tầng" are three **layers of evidence/demo** (Tầng 1 bắt buộc, Tầng 2 tùy chọn nhưng nên có, Tầng 3 chạy trước và chụp kết quả cho báo cáo). Say this explicitly, with a short table (purpose, mandatory or not, when to run).
2. Add a **Wireshark section** (currently missing entirely). Content: capture on the real Wi-Fi/Ethernet adapter (two-laptop setup); display filters `udp.port == 5005` and `frame contains "SAP1"`; how to read the 19-byte header in the hex dump (first 4 bytes `53 41 50 31`); what to point out to the instructor (META, then CHUNK packets, NACK and retransmitted CHUNKs when Clumsy is on). Add a note that single-machine loopback capture needs the Npcap loopback adapter.
3. Add a **Two-laptop LAN checklist** (do these before the demo):
   - Both laptops on the same network/subnet; get IPv4 via `ipconfig`; verify with `ping`.
   - Windows Firewall on the receiver laptop: allow inbound UDP 5005 on the Private profile. Give the admin command: `netsh advfirewall firewall add rule name="SAP UDP 5005" dir=in action=allow protocol=UDP localport=5005 profile=private`
   - Warn about Wi-Fi AP/client isolation (school or public Wi-Fi) blocking device-to-device traffic; fallback is a phone hotspot or an Ethernet cable.
   - Make sure the network is set to **Private**, not Public.
   - Clumsy needs to run on **one** laptop only, as Administrator, with the existing filter.
   - Dry-run the full demo once on the actual two laptops the day before.
4. Update the Q&A section with the honest framing below (item "UDP vs TCP"), and add an "Limitations" item (no congestion control, no flow control, no encryption/authentication, unicast only, simplified selective-NACK ARQ).

### Replacement text for the "UDP vs TCP" Q&A answer
- UDP is connectionless with no delivery or ordering guarantee and no built-in retransmission; that is why it has low overhead. It still has a checksum that discards corrupted datagrams, so the problem is lost/reordered datagrams, not silent corruption.
- SAP adds on top: chunking under MTU, sequence numbers, per-chunk and whole-image CRC32, selective NACK and retransmission, bounded retries.
- We chose UDP **for the learning objective**: TCP does all of this inside the kernel, so building it ourselves exposes the transport-layer mechanisms.
- In a production system sending a single alert image, TCP (or QUIC) would normally be the right engineering choice; re-implementing reliability over UDP is only justified for course purposes or special latency/multicast needs.

## Out of scope (do not implement)
- Broadcast/multicast, encryption, a phone app, any HTTP/web server component, changes to the SAP header.

## Acceptance criteria
- [ ] Receiver on laptop B and sender on laptop A communicate using B's LAN IP; receiver does not need to run on the same machine.
- [ ] Sender can target 2+ receivers; killing one receiver does not stop delivery to the other.
- [ ] `python -m pytest -v network/tests/test_reliability.py` passes, including the new multi-receiver test.
- [ ] `DEMO_RUNBOOK.md` contains the Wireshark section, the two-laptop checklist, the corrected tier explanation and the updated Q&A.
- [ ] Final report lists exactly which files changed and which Step 0 items were already satisfied.