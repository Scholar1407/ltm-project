"""
Smoke Alert Protocol (SAP) - Automated Reliability & Correctness Tests
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 7

Deterministic testing using socket-layer fault injection:
- Happy-path delivery verification
- Deterministic packet dropping (e.g. seq 5 and seq 20 on 1st attempt only)
- NACK generation, selective retransmission, and byte-for-byte reassembly verification
- CRC32 integrity validation
"""

from pathlib import Path
import subprocess
import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import queue
import socket
import threading
import time
from typing import Dict, List, Set, Tuple
import pytest

from network.shared.protocol import (
    HEADER_SIZE,
    MAGIC,
    MAX_PAYLOAD,
    Packet,
    PacketType,
    compute_crc32,
    pack_nack_payload,
    pack_packet,
    split_into_chunks,
    unpack_nack_payload,
    unpack_packet,
)
from network.sender.sender import SmokeAlertSender
from network.sender.discovery import DiscoveryListener
from network.receiver.receiver import DiscoveryBeaconThread, SmokeAlertReceiver


class FaultInjectingSocket:
    """
    A wrapper around a standard UDP socket that deterministically drops
    or corrupts specified chunk sequence numbers on designated attempt numbers.
    """

    def __init__(
        self,
        real_sock: socket.socket,
        drop_chunks_on_attempt: Dict[int, int] = None,  # {seq: attempt_to_drop (1-indexed)}
        corrupt_chunks_on_attempt: Dict[int, int] = None,
    ):
        self._sock = real_sock
        self.drop_map = drop_chunks_on_attempt or {}
        self.corrupt_map = corrupt_chunks_on_attempt or {}

        # Tracking state
        self.send_attempts: Dict[Tuple[int, int], int] = {}  # (img_id, seq) -> count
        self.dropped_chunks: List[Tuple[int, int]] = []
        self.corrupted_chunks: List[Tuple[int, int]] = []
        self.retransmitted_seqs: List[int] = []

    def __getattr__(self, name):
        return getattr(self._sock, name)

    def sendto(self, data: bytes, addr) -> int:
        try:
            pkt = unpack_packet(data)
        except Exception:
            # Non-protocol or malformed data passes through
            return self._sock.sendto(data, addr)

        if pkt.is_chunk:
            key = (pkt.img_id, pkt.seq)
            count = self.send_attempts.get(key, 0) + 1
            self.send_attempts[key] = count

            if count > 1:
                self.retransmitted_seqs.append(pkt.seq)

            # Check for deterministic drop
            if pkt.seq in self.drop_map and count == self.drop_map[pkt.seq]:
                self.dropped_chunks.append((pkt.img_id, pkt.seq))
                # Silently drop packet by returning byte count without calling real socket
                return len(data)

            # Check for deterministic corruption
            if pkt.seq in self.corrupt_map and count == self.corrupt_map[pkt.seq]:
                self.corrupted_chunks.append((pkt.img_id, pkt.seq))
                # Corrupt the payload so CRC check fails
                corrupted_payload = bytearray(pkt.payload)
                if corrupted_payload:
                    corrupted_payload[0] ^= 0xFF
                corrupted_pkt = pack_packet(
                    pkt.pkt_type,
                    pkt.img_id,
                    pkt.seq,
                    pkt.total,
                    pkt.crc32,  # original CRC with mutated payload triggers CRC mismatch
                    bytes(corrupted_payload),
                )
                return self._sock.sendto(corrupted_pkt, addr)

        return self._sock.sendto(data, addr)


def generate_synthetic_image(num_chunks: int = 30) -> bytes:
    """Generates synthetic byte data guaranteeing a specific number of chunks."""
    size = num_chunks * MAX_PAYLOAD - 250  # 30 chunks total
    pattern = b"SMOKE_ALERT_SYNTHETIC_FRAME_DATA_" * (size // 33 + 1)
    return pattern[:size]


# -------------------------------------------------------------------------
# Test Cases
# -------------------------------------------------------------------------

def test_protocol_pack_unpack():
    """Validates low-level header structure, byte ordering, and bounds checking."""
    img_id = 4821
    seq = 45
    total = 134
    payload = b"X" * 1200
    crc = compute_crc32(payload)

    packed = pack_packet(PacketType.CHUNK, img_id, seq, total, crc, payload)
    assert len(packed) == HEADER_SIZE + len(payload)

    pkt = unpack_packet(packed)
    assert pkt.magic == MAGIC
    assert pkt.pkt_type == PacketType.CHUNK
    assert pkt.img_id == img_id
    assert pkt.seq == seq
    assert pkt.total == total
    assert pkt.payload_len == len(payload)
    assert pkt.crc32 == crc
    assert pkt.payload == payload


def test_nack_payload_serialization():
    """Validates missing chunk sequence number serialization and deserialization."""
    missing = [5, 20, 42, 105, 999]
    payload = pack_nack_payload(missing)
    assert len(payload) == len(missing) * 2

    unpacked = unpack_nack_payload(payload)
    assert unpacked == missing


def test_happy_path_transmission():
    """
    Validates Layer 1 Happy Path: All packets arrive without loss.
    Asserts zero retransmissions and exact byte-for-byte fidelity.
    """
    port = 5901
    original_data = generate_synthetic_image(num_chunks=15)
    img_id = 7001
    received_container = {}

    def on_recv(i_id, data, ts):
        received_container[i_id] = data

    receiver = SmokeAlertReceiver(
        listen_host="127.0.0.1",
        listen_port=port,
        on_image_received=on_recv,
    )
    receiver.start()

    try:
        sender = SmokeAlertSender(
            target_host="127.0.0.1",
            target_port=port,
            wait_timeout=0.4,
        )
        success = sender.send_image(img_id, original_data, "2026-10-07 10:00:00")
        sender.close()

        assert success is True
        assert img_id in received_container
        assert received_container[img_id] == original_data
        assert compute_crc32(received_container[img_id]) == compute_crc32(original_data)
    finally:
        receiver.stop()


def test_selective_loss_and_nack_retransmission():
    """
    Validates Layer 3 Specification requirement (Section 7):
    Deterministically drops sequence 5 and sequence 20 on the first send attempt only.
    Asserts:
    - The receiver's reassembled image byte-for-byte matches the original.
    - Exactly one retransmission round occurred for the dropped sequence numbers (seq 5 and 20).
    - CRC32 check passes.
    """
    port = 5902
    original_data = generate_synthetic_image(num_chunks=25)
    img_id = 7002
    received_container = {}

    def on_recv(i_id, data, ts):
        received_container[i_id] = data

    receiver = SmokeAlertReceiver(
        listen_host="127.0.0.1",
        listen_port=port,
        inactivity_timeout=0.2,  # 200ms inactivity timeout for fast test execution
        on_image_received=on_recv,
    )
    receiver.start()

    raw_sender_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw_sender_sock.settimeout(0.5)

    # Wrap sender socket to deterministically drop seq 5 and seq 20 on attempt 1
    wrapped_sock = FaultInjectingSocket(
        real_sock=raw_sender_sock,
        drop_chunks_on_attempt={5: 1, 20: 1},
    )

    try:
        sender = SmokeAlertSender(
            target_host="127.0.0.1",
            target_port=port,
            wait_timeout=0.5,
            sock=wrapped_sock,
        )

        success = sender.send_image(img_id, original_data, "2026-10-07 10:05:00")
        sender.close()

        # 1. Assert transmission succeeded
        assert success is True

        # 2. Assert dropped exactly seq 5 and seq 20 on first attempt
        assert (img_id, 5) in wrapped_sock.dropped_chunks
        assert (img_id, 20) in wrapped_sock.dropped_chunks
        assert len(wrapped_sock.dropped_chunks) == 2

        # 3. Assert exactly one retransmission round occurred for seq 5 and seq 20
        assert 5 in wrapped_sock.retransmitted_seqs
        assert 20 in wrapped_sock.retransmitted_seqs
        assert wrapped_sock.send_attempts[(img_id, 5)] == 2
        assert wrapped_sock.send_attempts[(img_id, 20)] == 2

        # 4. Assert receiver reassembled byte-for-byte identical image
        assert img_id in received_container
        assert received_container[img_id] == original_data

        # 5. Assert CRC32 integrity check passes
        assert compute_crc32(received_container[img_id]) == compute_crc32(original_data)
    finally:
        receiver.stop()


def test_corrupted_chunk_dropped_and_recovered():
    """
    Validates Section 4: A corrupted chunk payload fails per-chunk CRC,
    is dropped silently by the receiver, and recovered via NACK.
    """
    port = 5903
    original_data = generate_synthetic_image(num_chunks=10)
    img_id = 7003
    received_container = {}

    def on_recv(i_id, data, ts):
        received_container[i_id] = data

    receiver = SmokeAlertReceiver(
        listen_host="127.0.0.1",
        listen_port=port,
        inactivity_timeout=0.2,
        on_image_received=on_recv,
    )
    receiver.start()

    raw_sender_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw_sender_sock.settimeout(0.5)

    # Corrupt chunk 3 on attempt 1
    wrapped_sock = FaultInjectingSocket(
        real_sock=raw_sender_sock,
        corrupt_chunks_on_attempt={3: 1},
    )

    try:
        sender = SmokeAlertSender(
            target_host="127.0.0.1",
            target_port=port,
            wait_timeout=0.5,
            sock=wrapped_sock,
        )

        success = sender.send_image(img_id, original_data, "2026-10-07 10:10:00")
        sender.close()

        assert success is True
        assert (img_id, 3) in wrapped_sock.corrupted_chunks
        assert 3 in wrapped_sock.retransmitted_seqs
        assert img_id in received_container
        assert received_container[img_id] == original_data
        assert compute_crc32(received_container[img_id]) == compute_crc32(original_data)
    finally:
        receiver.stop()


def test_multi_receiver_selective_loss():
    """
    Task 2 requirement:
    Two receivers running concurrently:
    - Receiver 1 operates over a clean link (0 dropped packets, 0 retransmissions).
    - Receiver 2 operates over a lossy link with deterministic drops on seq 4 and seq 12.
    Asserts:
    - Both receivers end up with byte-identical reassembled images matching original.
    - Both pass CRC32 integrity check.
    - Only the lossy receiver's worker performed a retransmit round.
    """
    port1 = 5911
    port2 = 5912
    original_data = generate_synthetic_image(num_chunks=20)
    img_id = 8001
    recv1_container = {}
    recv2_container = {}

    def on_recv1(i_id, data, ts):
        recv1_container[i_id] = data

    def on_recv2(i_id, data, ts):
        recv2_container[i_id] = data

    receiver1 = SmokeAlertReceiver(
        listen_host="127.0.0.1",
        listen_port=port1,
        inactivity_timeout=0.2,
        on_image_received=on_recv1,
    )
    receiver2 = SmokeAlertReceiver(
        listen_host="127.0.0.1",
        listen_port=port2,
        inactivity_timeout=0.2,
        on_image_received=on_recv2,
    )

    receiver1.start()
    receiver2.start()

    # Track sockets per receiver endpoint
    raw_sock1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw_sock1.settimeout(0.5)
    wrapped_sock1 = FaultInjectingSocket(real_sock=raw_sock1)

    raw_sock2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    raw_sock2.settimeout(0.5)
    wrapped_sock2 = FaultInjectingSocket(
        real_sock=raw_sock2,
        drop_chunks_on_attempt={4: 1, 12: 1},
    )

    socket_map = {
        ("127.0.0.1", port1): wrapped_sock1,
        ("127.0.0.1", port2): wrapped_sock2,
    }

    def sock_factory(endpoint: Tuple[str, int]) -> socket.socket:
        return socket_map[endpoint]

    try:
        sender = SmokeAlertSender(
            receivers=[("127.0.0.1", port1), ("127.0.0.1", port2)],
            wait_timeout=0.5,
            sock_factory=sock_factory,
        )

        success = sender.send_image(img_id, original_data, "2026-10-08 14:00:00")
        sender.close()

        # 1. Overall fan-out success
        assert success is True
        assert sender.last_results[("127.0.0.1", port1)] is True
        assert sender.last_results[("127.0.0.1", port2)] is True

        # 2. Both receivers received byte-identical images
        assert img_id in recv1_container
        assert recv1_container[img_id] == original_data
        assert compute_crc32(recv1_container[img_id]) == compute_crc32(original_data)

        assert img_id in recv2_container
        assert recv2_container[img_id] == original_data
        assert compute_crc32(recv2_container[img_id]) == compute_crc32(original_data)

        # 3. Clean link to receiver 1: 0 drops, 0 retransmissions
        assert len(wrapped_sock1.dropped_chunks) == 0
        assert len(wrapped_sock1.retransmitted_seqs) == 0

        # 4. Lossy link to receiver 2: dropped seq 4 and 12, exactly retransmitted seq 4 and 12
        assert (img_id, 4) in wrapped_sock2.dropped_chunks
        assert (img_id, 12) in wrapped_sock2.dropped_chunks
        assert 4 in wrapped_sock2.retransmitted_seqs
        assert 12 in wrapped_sock2.retransmitted_seqs
        assert wrapped_sock2.send_attempts[(img_id, 4)] == 2
        assert wrapped_sock2.send_attempts[(img_id, 12)] == 2

    finally:
        receiver1.stop()
        receiver2.stop()
        raw_sock1.close()
        raw_sock2.close()


def test_multi_receiver_dead_node_tolerance():
    """
    Task 2 requirement:
    Killing one receiver does not stop or block delivery to the other.
    Target 1: Active receiver (port 5915)
    Target 2: Dead receiver (port 5916, nobody listening)
    """
    alive_port = 5915
    dead_port = 5916
    original_data = generate_synthetic_image(num_chunks=10)
    img_id = 8002
    alive_container = {}

    def on_recv(i_id, data, ts):
        alive_container[i_id] = data

    receiver = SmokeAlertReceiver(
        listen_host="127.0.0.1",
        listen_port=alive_port,
        inactivity_timeout=0.2,
        on_image_received=on_recv,
    )
    receiver.start()

    try:
        sender = SmokeAlertSender(
            receivers=[("127.0.0.1", alive_port), ("127.0.0.1", dead_port)],
            wait_timeout=0.2,
            max_retries=1,  # Short retry count so dead worker terminates quickly
        )

        success = sender.send_image(img_id, original_data, "2026-10-08 14:05:00")
        sender.close()

        # Surviving receiver gets complete image regardless of dead receiver
        assert success is True
        assert sender.last_results[("127.0.0.1", alive_port)] is True
        assert sender.last_results[("127.0.0.1", dead_port)] is False
        assert img_id in alive_container
        assert alive_container[img_id] == original_data
        assert compute_crc32(alive_container[img_id]) == compute_crc32(original_data)

    finally:
        receiver.stop()


def test_stdlib_only_imports_in_cores():
    """
    Task 4 requirement:
    Verify network/receiver/receiver.py, network/sender/sender.py,
    network/receiver/cli.py, and network/sender/cli.py import only
    standard library + network.shared.protocol.
    Asserts that blocking tkinter, cv2, numpy, PIL, and ultralytics does not prevent import.
    """
    probe_code = (
        "import sys\n"
        "for mod in ['tkinter', 'cv2', 'numpy', 'PIL', 'ultralytics']:\n"
        "    sys.modules[mod] = None\n"
        "import network.receiver.receiver\n"
        "import network.sender.sender\n"
        "import network.receiver.cli\n"
        "import network.sender.cli\n"
        "import network.sender.discovery\n"
        "import network.shared.protocol\n"
        "print('SUCCESS')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe_code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Import failed under blocked external modules: {result.stderr}"
    assert "SUCCESS" in result.stdout


def test_cli_loopback_and_notify_cmd(tmp_path):
    """
    Task 4 requirement:
    Runs receiver CLI and sender CLI over loopback with a temp directory.
    Asserts:
    - --send-file delivers a byte-identical JPEG.
    - --notify-cmd fires once per completed transfer with substituted placeholders.
    """
    port = 5930
    out_dir = tmp_path / "received"
    sample_file = tmp_path / "sample.jpg"
    test_data = (
        b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xDB\x00C\x00"
        + (b"CLI_TEST_JPEG_DATA_" * 250)
        + b"\xFF\xD9"
    )
    sample_file.write_bytes(test_data)

    notif_file = tmp_path / "notified.txt"
    helper_script = tmp_path / "record.py"
    helper_script.write_text(
        "import sys\n"
        "with open(sys.argv[1], 'a', encoding='utf-8') as f:\n"
        "    f.write(f'{sys.argv[2]}|{sys.argv[3]}|{sys.argv[4]}\\n')\n",
        encoding="utf-8",
    )

    notify_template = (
        f'"{sys.executable}" "{helper_script.resolve()}" "{notif_file.resolve()}" '
        f'"{{path}}" "{{img_id}}" "{{sender}}"'
    )

    # Launch receiver CLI as a background subprocess
    rcv_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "network.receiver.cli",
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--out",
            str(out_dir),
            "--notify-cmd",
            notify_template,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        time.sleep(0.6)  # Allow socket to bind and start loop

        # Run sender CLI
        snd_result = subprocess.run(
            [
                sys.executable,
                "-m",
                "network.sender.cli",
                "--to",
                f"127.0.0.1:{port}",
                "--send-file",
                str(sample_file),
                "--img-id",
                "9050",
            ],
            capture_output=True,
            text=True,
        )

        assert snd_result.returncode == 0, f"Sender CLI failed: {snd_result.stderr}"

        # Wait briefly for notify subprocess to finish writing
        time.sleep(0.6)

        # 1. Assert received file matches byte-for-byte
        received_files = list(out_dir.glob("*_9050.jpg"))
        assert len(received_files) == 1
        assert received_files[0].read_bytes() == test_data

        # 2. Assert notify command was triggered with placeholders substituted
        assert notif_file.exists()
        log_lines = notif_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(log_lines) == 1
        saved_path, img_id_str, sender_ep = log_lines[0].split("|")
        assert img_id_str == "9050"
        assert "127.0.0.1" in sender_ep
        assert Path(saved_path).resolve() == received_files[0].resolve()

    finally:
        rcv_proc.terminate()
        try:
            rcv_proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            rcv_proc.kill()


class MockDiscoverySocket:
    """Mock UDP socket simulating LAN broadcast discovery exchanges."""

    def __init__(self, beacon_sender_ip: str = "192.168.1.77", beacon_data_port: int = 5005):
        self.beacon_sender_ip = beacon_sender_ip
        self.beacon_data_port = beacon_data_port
        self.sent_packets: List[Tuple[bytes, Tuple[str, int]]] = []
        self.recv_queue: queue.Queue = queue.Queue()
        self.closed = False

    def setsockopt(self, *args, **kwargs):
        pass

    def bind(self, addr):
        pass

    def settimeout(self, timeout):
        pass

    def sendto(self, data: bytes, addr: Tuple[str, int]):
        self.sent_packets.append((data, addr))
        try:
            pkt = unpack_packet(data)
            if pkt.pkt_type == PacketType.PROBE:
                # Simulates receiver responding with a BEACON packet
                beacon_pkt = pack_packet(
                    pkt_type=PacketType.BEACON,
                    img_id=self.beacon_data_port,
                    seq=0,
                    total=0,
                    crc32=0,
                    payload=b"",
                )
                self.recv_queue.put((beacon_pkt, (self.beacon_sender_ip, 5006)))
        except Exception:
            pass
        return len(data)

    def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
        try:
            return self.recv_queue.get(timeout=0.2)
        except queue.Empty:
            raise socket.timeout()

    def close(self):
        self.closed = True


def test_discovery_probe_and_beacon_mocked():
    """
    Task B acceptance criteria:
    Mock the UDP socket layer, assert that a PROBE sent by DiscoveryListener
    results in a discovered peer when a BEACON is received in reply.
    Also validates TTL expiration behavior.
    """
    mock_sock = MockDiscoverySocket(beacon_sender_ip="192.168.1.77", beacon_data_port=5005)
    listener = DiscoveryListener(
        discovery_port=5006,
        peer_ttl=2.0,
        probe_interval=10.0,
        sock=mock_sock,
    )

    listener.start()
    try:
        # Give worker a moment to send initial probe and process beacon reply
        time.sleep(0.3)

        # 1. Assert PROBE packet was sent
        assert len(mock_sock.sent_packets) > 0
        probe_raw, target_addr = mock_sock.sent_packets[0]
        probe_pkt = unpack_packet(probe_raw)
        assert probe_pkt.pkt_type == PacketType.PROBE
        assert probe_pkt.magic == MAGIC

        # 2. Assert peer was discovered with data port 5005
        receivers = listener.get_receivers()
        assert ("192.168.1.77", 5005) in receivers

        # 3. Assert detailed status for UI
        peers = listener.get_discovered_peers()
        assert len(peers) == 1
        assert peers[0]["host"] == "192.168.1.77"
        assert peers[0]["port"] == 5005
        assert peers[0]["is_active"] is True

        # 4. Assert peer TTL expiration (> 2.0s)
        # Advance peer timestamp into the past
        with listener._lock:
            listener._peers[("192.168.1.77", 5005)] = time.monotonic() - 5.0

        expired_receivers = listener.get_receivers()
        assert ("192.168.1.77", 5005) not in expired_receivers
        assert len(expired_receivers) == 0

    finally:
        listener.stop()


def test_discovery_beacon_thread_reply_to_probe():
    """
    Validates receiver DiscoveryBeaconThread:
    When a PROBE packet is received from a sender, it unicasts a BEACON
    packet back to the sender containing the receiver's data port in img_id.
    """
    class MockBeaconSocket:
        def __init__(self):
            self.incoming: queue.Queue = queue.Queue()
            self.replies: List[Tuple[bytes, Tuple[str, int]]] = []

        def setsockopt(self, *args, **kwargs):
            pass

        def bind(self, addr):
            pass

        def settimeout(self, timeout):
            pass

        def sendto(self, data: bytes, addr: Tuple[str, int]):
            self.replies.append((data, addr))
            return len(data)

        def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
            try:
                return self.incoming.get(timeout=0.1)
            except queue.Empty:
                raise socket.timeout()

        def close(self):
            pass

    mock_sock = MockBeaconSocket()
    beacon_thread = DiscoveryBeaconThread(
        data_port=5005,
        discovery_port=5006,
        beacon_interval=10.0,
        sock=mock_sock,
    )
    beacon_thread.start()

    try:
        time.sleep(0.1)  # allow startup broadcast

        # Inject incoming PROBE from sender at 192.168.1.55:5006
        probe_pkt = pack_packet(PacketType.PROBE, 0, 0, 0, 0, b"")
        mock_sock.incoming.put((probe_pkt, ("192.168.1.55", 5006)))

        # Wait for reply
        time.sleep(0.2)

        # Find reply to 192.168.1.55:5006
        reply_found = False
        for raw, addr in mock_sock.replies:
            if addr == ("192.168.1.55", 5006):
                pkt = unpack_packet(raw)
                assert pkt.pkt_type == PacketType.BEACON
                assert pkt.img_id == 5005  # carries receiver's data port
                reply_found = True
                break

        assert reply_found is True, "DiscoveryBeaconThread did not send unicast BEACON reply to sender"

    finally:
        beacon_thread.stop()



