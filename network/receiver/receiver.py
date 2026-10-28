"""
Smoke Alert Protocol (SAP) - Receiver Implementation
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 4 & Section 5
"""

from __future__ import annotations
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from ..shared.protocol import (
        DISCOVERY_PORT,
        HEADER_SIZE,
        Packet,
        PacketType,
        compute_crc32,
        get_local_ipv4_addresses,
        log_drop_chunk,
        log_info,
        log_recv_chunk,
        log_send_ack,
        log_send_nack,
        pack_nack_payload,
        pack_packet,
        unpack_packet,
    )
except (ImportError, ValueError):
    from network.shared.protocol import (
        DISCOVERY_PORT,
        HEADER_SIZE,
        Packet,
        PacketType,
        compute_crc32,
        get_local_ipv4_addresses,
        log_drop_chunk,
        log_info,
        log_recv_chunk,
        log_send_ack,
        log_send_nack,
        pack_nack_payload,
        pack_packet,
        unpack_packet,
    )


class DiscoveryBeaconThread(threading.Thread):
    """
    Listens on UDP 5006 for PROBE packets and responds with BEACON.
    Also broadcasts BEACON on startup and every BEACON_INTERVAL seconds.
    """
    BEACON_INTERVAL = 5.0   # seconds between unsolicited beacons
    DISCOVERY_PORT  = 5006

    def __init__(
        self,
        data_port: int = 5005,
        discovery_port: int = 5006,
        beacon_interval: float = 5.0,
        sock: Optional[socket.socket] = None,
        log_callback: Optional[LogCallback] = None,
    ):
        super().__init__(daemon=True)
        self.data_port = data_port
        self.discovery_port = discovery_port
        self.beacon_interval = beacon_interval
        self._sock = sock
        self._own_socket = sock is None
        self._running = False
        self.log_callback = log_callback

    def stop(self):
        self._running = False
        if self._own_socket and self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def run(self):
        self._running = True
        if self._sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            try:
                sock.bind(("0.0.0.0", self.discovery_port))
            except Exception as e:
                log_info(
                    f"Discovery beacon bind note on port {self.discovery_port}: {e}",
                    self.log_callback,
                )
                return
            sock.settimeout(1.0)
            self._sock = sock
        else:
            sock = self._sock

        beacon_pkt = pack_packet(
            PacketType.BEACON,
            img_id=self.data_port,
            seq=0,
            total=0,
            crc32=0,
            payload=b"",
        )

        def _get_destinations():
            dests = {"255.255.255.255", "<broadcast>", "127.0.0.1"}
            try:
                for ip in get_local_ipv4_addresses():
                    parts = ip.split(".")
                    if len(parts) == 4:
                        dests.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
            except Exception:
                pass
            return [(d, self.discovery_port) for d in dests]

        # Startup beacon broadcast
        for target in _get_destinations():
            try:
                sock.sendto(beacon_pkt, target)
            except Exception:
                pass

        last_beacon = time.monotonic()
        while self._running:
            try:
                raw, addr = sock.recvfrom(256)
                pkt = unpack_packet(raw)
                if pkt.pkt_type == PacketType.PROBE:
                    try:
                        sock.sendto(beacon_pkt, addr)  # unicast reply to sender
                    except Exception:
                        pass
                    # Also broadcast response to cover same-host or multi-homed interfaces immediately
                    for target in _get_destinations():
                        try:
                            sock.sendto(beacon_pkt, target)
                        except Exception:
                            pass
            except (socket.timeout, BlockingIOError):
                pass
            except Exception:
                pass

            if time.monotonic() - last_beacon >= self.beacon_interval:
                for target in _get_destinations():
                    try:
                        sock.sendto(beacon_pkt, target)
                    except Exception:
                        pass
                last_beacon = time.monotonic()

        if self._own_socket and self._sock:
            try:
                self._sock.close()
            except Exception:
                pass


@dataclass
class ReassemblySession:
    img_id: int
    sender_addr: Tuple[str, int]
    total: int
    expected_crc32: Optional[int] = None
    chunks: List[Optional[bytes]] = field(default_factory=list)
    last_activity_time: float = field(default_factory=time.monotonic)
    nack_attempts: int = 0
    completed: bool = False
    timestamp_meta: str = ""
    full_image_bytes: Optional[bytes] = None

    def missing_indices(self) -> List[int]:
        return [i for i, c in enumerate(self.chunks) if c is None]

    def is_complete(self) -> bool:
        return (
            self.total > 0
            and len(self.chunks) == self.total
            and all(c is not None for c in self.chunks)
            and self.expected_crc32 is not None
        )


ImageReceivedCallback = Callable[[int, bytes, str], None]
TransferCompleteCallback = Callable[[Tuple[str, int], int, bytes, Dict[str, Any]], None]
LogCallback = Callable[[str], None]


class SmokeAlertReceiver:
    """
    Listens for incoming smoking alert images over UDP via the Smoke Alert Protocol (SAP).
    Handles reassembly, per-chunk CRC verification, missing chunk NACK generation,
    and end-to-end CRC32 verification before triggering alert notifications.
    """

    def __init__(
        self,
        listen_host: str = "0.0.0.0",
        listen_port: int = 5005,
        inactivity_timeout: float = 0.3,  # 300ms inactivity timeout per spec
        max_retries: int = 5,
        sock: Optional[socket.socket] = None,
        on_image_received: Optional[ImageReceivedCallback] = None,
        on_transfer_complete: Optional[TransferCompleteCallback] = None,
        log_callback: Optional[LogCallback] = None,
        enable_discovery: bool = True,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.inactivity_timeout = inactivity_timeout
        self.max_retries = max_retries
        self.on_image_received = on_image_received
        self.on_transfer_complete = on_transfer_complete
        self.log_callback = log_callback
        self.enable_discovery = enable_discovery

        self._own_socket = sock is None
        if sock is not None:
            self.sock = sock
        else:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.listen_host, self.listen_port))
            # Set short poll timeout so thread can periodically check inactivity timers
            self.sock.settimeout(0.05)

        # Keyed by ((sender_ip, sender_port), img_id) to isolate concurrent streams from multiple senders
        self.sessions: Dict[Tuple[Tuple[str, int], int], ReassemblySession] = {}
        self.running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.beacon_thread: Optional[DiscoveryBeaconThread] = None

    def start(self):
        """Starts the receiver loop in a background thread."""
        if self.running:
            return
        self.running = True
        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

        if self.enable_discovery:
            self.beacon_thread = DiscoveryBeaconThread(
                data_port=self.listen_port,
                log_callback=self.log_callback,
            )
            self.beacon_thread.start()

        local_ips = get_local_ipv4_addresses()
        log_info(
            f"Receiver bound to {self.listen_host}:{self.listen_port} (inactivity={int(self.inactivity_timeout*1000)}ms)",
            self.log_callback,
        )
        log_info(
            f"Local IPv4 address(es) for LAN connections: {', '.join(local_ips)}",
            self.log_callback,
        )

    def stop(self):
        """Stops the receiver loop and releases socket resources."""
        self.running = False
        if self.beacon_thread:
            self.beacon_thread.stop()
            self.beacon_thread = None
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        if self._own_socket and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        log_info("Receiver stopped.", self.log_callback)

    def close(self):
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def _run_loop(self):
        """Main packet reception and inactivity monitoring loop."""
        while self.running:
            now = time.monotonic()

            # 1. Non-blocking packet receive step
            try:
                raw_data, addr = self.sock.recvfrom(65535)
                self._handle_incoming_packet(raw_data, addr, now)
            except (socket.timeout, BlockingIOError):
                pass
            except Exception as e:
                if self.running:
                    log_info(f"Socket receive error: {e}", self.log_callback)

            # 2. Inactivity timer check across all pending sessions
            self._check_session_timeouts(now)

    def _handle_incoming_packet(self, raw_data: bytes, addr: Tuple[str, int], now: float):
        try:
            packet = unpack_packet(raw_data)
        except Exception as e:
            log_info(f"Dropped malformed packet from {addr}: {e}", self.log_callback)
            return

        with self._lock:
            session_key = (addr, packet.img_id)

            # -------------------------------------------------------------
            # Case 1: META packet
            # -------------------------------------------------------------
            if packet.is_meta:
                session = self.sessions.get(session_key)
                if session and session.completed:
                    # If already completed, sender might have lost our ACK -> re-send ACK
                    self._send_ack(session, addr)
                    return

                if not session:
                    session = ReassemblySession(
                        img_id=packet.img_id,
                        sender_addr=addr,
                        total=packet.total,
                        expected_crc32=packet.crc32,
                        chunks=[None] * packet.total,
                        last_activity_time=now,
                        timestamp_meta=packet.payload.decode("utf-8", errors="replace"),
                    )
                    self.sessions[session_key] = session
                else:
                    # Update metadata on existing session
                    session.sender_addr = addr
                    session.total = packet.total
                    session.expected_crc32 = packet.crc32
                    session.last_activity_time = now
                    if packet.payload:
                        session.timestamp_meta = packet.payload.decode("utf-8", errors="replace")
                    if len(session.chunks) < packet.total:
                        session.chunks.extend([None] * (packet.total - len(session.chunks)))

                # Check if buffer was already full from prior chunks
                if session.is_complete():
                    self._finalize_and_verify(session, addr)

            # -------------------------------------------------------------
            # Case 2: CHUNK packet
            # -------------------------------------------------------------
            elif packet.is_chunk:
                # Per Section 4: Verify chunk's own CRC32. Silently drop if corrupted.
                actual_chunk_crc = compute_crc32(packet.payload)
                if actual_chunk_crc != packet.crc32:
                    log_drop_chunk(
                        packet.img_id,
                        packet.seq,
                        packet.total,
                        "corrupted crc",
                        self.log_callback,
                        peer=addr,
                    )
                    return

                session = self.sessions.get(session_key)
                if not session:
                    # Chunk arrived before META
                    session = ReassemblySession(
                        img_id=packet.img_id,
                        sender_addr=addr,
                        total=packet.total,
                        expected_crc32=None,
                        chunks=[None] * packet.total,
                        last_activity_time=now,
                    )
                    self.sessions[session_key] = session

                if session.completed:
                    # Already completed session: acknowledge sender
                    self._send_ack(session, addr)
                    return

                # Store payload at seq index
                if 0 <= packet.seq < session.total:
                    session.chunks[packet.seq] = packet.payload
                    session.last_activity_time = now
                    session.sender_addr = addr
                    log_recv_chunk(
                        packet.img_id,
                        packet.seq,
                        session.total,
                        self.log_callback,
                        peer=addr,
                    )

                # Check for completion
                if session.is_complete():
                    self._finalize_and_verify(session, addr)

    def _finalize_and_verify(self, session: ReassemblySession, addr: Tuple[str, int]):
        """Concatenates chunks, validates whole-image CRC32, and issues ACK."""
        if not session.is_complete():
            return

        full_image = b"".join(c for c in session.chunks if c is not None)
        calculated_whole_crc = compute_crc32(full_image)

        if calculated_whole_crc == session.expected_crc32:
            session.completed = True
            session.full_image_bytes = full_image

            # Trigger notification callbacks before acknowledging sender
            if self.on_image_received:
                try:
                    self.on_image_received(
                        session.img_id, full_image, session.timestamp_meta
                    )
                except Exception as e:
                    log_info(
                        f"Error in on_image_received callback: {e}", self.log_callback
                    )

            if self.on_transfer_complete:
                try:
                    stats = {
                        "total": session.total,
                        "crc32": session.expected_crc32,
                        "nack_attempts": session.nack_attempts,
                        "size": len(full_image),
                        "timestamp": session.timestamp_meta,
                    }
                    self.on_transfer_complete(addr, session.img_id, full_image, stats)
                except Exception as e:
                    log_info(
                        f"Error in on_transfer_complete callback: {e}", self.log_callback
                    )

            self._send_ack(session, addr)
        else:
            # End-to-end CRC mismatch: request full resend via NACK
            log_info(
                f"[CRC-FAIL] img_id={session.img_id} from {addr} expected=0x{session.expected_crc32:08x} got=0x{calculated_whole_crc:08x}. Requesting full resend.",
                self.log_callback,
            )
            # Reset chunks
            session.chunks = [None] * session.total
            self._send_nack(session, list(range(session.total)), addr)

    def _send_ack(self, session: ReassemblySession, addr: Tuple[str, int]):
        ack_pkt = pack_packet(
            pkt_type=PacketType.ACK,
            img_id=session.img_id,
            seq=0,
            total=session.total,
            crc32=session.expected_crc32 or 0,
        )
        self.sock.sendto(ack_pkt, addr)
        log_send_ack(session.img_id, session.total, self.log_callback, peer=addr)

    def _send_nack(
        self, session: ReassemblySession, missing_seqs: List[int], addr: Tuple[str, int]
    ):
        nack_payload = pack_nack_payload(missing_seqs)
        nack_pkt = pack_packet(
            pkt_type=PacketType.NACK,
            img_id=session.img_id,
            seq=0,
            total=session.total,
            crc32=compute_crc32(nack_payload),
            payload=nack_payload,
        )
        self.sock.sendto(nack_pkt, addr)
        log_send_nack(session.img_id, missing_seqs, self.log_callback, peer=addr)

    def _check_session_timeouts(self, now: float):
        """Scans pending sessions; sends NACK when inactivity window is exceeded."""
        with self._lock:
            for session_key, session in list(self.sessions.items()):
                if session.completed:
                    continue

                idle_duration = now - session.last_activity_time
                if idle_duration >= self.inactivity_timeout:
                    missing = session.missing_indices()
                    if not missing:
                        continue

                    if session.nack_attempts < self.max_retries:
                        session.nack_attempts += 1
                        session.last_activity_time = now
                        self._send_nack(session, missing, session.sender_addr)
                    else:
                        sender_addr, img_id = session_key
                        log_info(
                            f"[TIMEOUT] img_id={img_id} from {sender_addr} exceeded max NACK attempts ({self.max_retries}). Discarding incomplete session.",
                            self.log_callback,
                        )
                        # Clean up failed session
                        del self.sessions[session_key]


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="SAP Smoke Alert Protocol Receiver CLI")
    parser.add_argument("--host", default="0.0.0.0", help="Listen IP address")
    parser.add_argument("--port", type=int, default=5005, help="Listen UDP port")
    parser.add_argument("--save-dir", default="received_alerts", help="Directory to save received images")
    args = parser.parse_args()

    import os
    os.makedirs(args.save_dir, exist_ok=True)

    def on_alert(img_id: int, img_bytes: bytes, timestamp: str):
        print(f"\n🔔 [ALERT EVENT RECEIVED] img_id={img_id} at {timestamp} ({len(img_bytes)} bytes)")
        out_filename = os.path.join(args.save_dir, f"alert_{img_id}.jpg")
        with open(out_filename, "wb") as f:
            f.write(img_bytes)
        print(f"Saved received alert image to: {out_filename}\n")

    receiver = SmokeAlertReceiver(
        listen_host=args.host,
        listen_port=args.port,
        on_image_received=on_alert,
    )

    receiver.start()
    print("Receiver running. Press Ctrl+C to exit...")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nStopping receiver...")
        receiver.stop()
