"""
Smoke Alert Protocol (SAP) - Receiver Discovery Service
Course: Network Programming (LTM)
Specification: prompt/upgrade-discovery-fps-prompt.md Task B

Discovers active SAP receivers on the LAN via UDP port 5006.
Sends PROBE broadcasts and collects unsolicited / responsive BEACON packets.
Provides a thread-safe snapshot of active receiver endpoints.
"""

from __future__ import annotations
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from ..shared.protocol import (
        DISCOVERY_PORT,
        Packet,
        PacketType,
        get_local_ipv4_addresses,
        pack_packet,
        unpack_packet,
    )
except (ImportError, ValueError):
    from network.shared.protocol import (
        DISCOVERY_PORT,
        Packet,
        PacketType,
        get_local_ipv4_addresses,
        pack_packet,
        unpack_packet,
    )


def get_broadcast_destinations(port: int) -> List[Tuple[str, int]]:
    """Calculates all broadcast targets across all active network interfaces."""
    destinations = {"255.255.255.255", "<broadcast>", "127.0.0.1"}
    try:
        for ip in get_local_ipv4_addresses():
            parts = ip.split(".")
            if len(parts) == 4:
                destinations.add(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
    except Exception:
        pass
    return [(d, port) for d in destinations]


class DiscoveryListener:
    """
    Discovers active SAP receivers on the LAN.
    Sends one PROBE on startup, then passively collects BEACON packets.
    Thread-safe: get_receivers() can be called from any thread.
    """

    DISCOVERY_PORT = 5006
    PEER_TTL = 30.0  # remove peer if no beacon heard for this many seconds
    PROBE_INTERVAL = 10.0  # re-probe every 10 seconds to detect newly-joined receivers

    def __init__(
        self,
        discovery_port: int = DISCOVERY_PORT,
        peer_ttl: float = PEER_TTL,
        probe_interval: float = PROBE_INTERVAL,
        sock: Optional[socket.socket] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        self.discovery_port = discovery_port
        self.peer_ttl = peer_ttl
        self.probe_interval = probe_interval
        self.sock = sock
        self._own_socket = sock is None
        self.log_callback = log_callback

        self._peers: Dict[Tuple[str, int], float] = {}  # (host, data_port) -> last_seen_monotonic
        self._lock = threading.Lock()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def start(self):
        """Starts discovery listener worker thread as a daemon."""
        if self._running:
            return
        self._running = True

        if self.sock is None:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            try:
                s.bind(("0.0.0.0", self.discovery_port))
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"[DISCOVERY] Bind notice on port {self.discovery_port}: {e}")
            s.settimeout(1.0)
            self.sock = s

        self._worker_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        """Stops listener thread and cleans up socket."""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
        if self._own_socket and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def probe(self):
        """Sends an immediate PROBE broadcast to locate SAP receivers."""
        if not self.sock:
            return
        probe_pkt = pack_packet(
            pkt_type=PacketType.PROBE,
            img_id=0,
            seq=0,
            total=0,
            crc32=0,
            payload=b"",
        )
        targets = get_broadcast_destinations(self.discovery_port)
        for target in targets:
            try:
                self.sock.sendto(probe_pkt, target)
            except Exception:
                pass

    def get_receivers(self) -> List[Tuple[str, int]]:
        """
        Thread-safe snapshot of all discovered active receivers.
        Returns peers whose last_seen timestamp is within PEER_TTL seconds.
        """
        now = time.monotonic()
        with self._lock:
            active = [
                ep
                for ep, last_seen in self._peers.items()
                if (now - last_seen) <= self.peer_ttl
            ]
        return active

    def get_discovered_peers(self) -> List[Dict[str, Any]]:
        """
        Returns rich details of all tracked peers (for UI display):
        [{"host": str, "port": int, "age": float, "is_active": bool}]
        Active if seen within 10.0s; stale if > 10.0s but <= PEER_TTL.
        """
        now = time.monotonic()
        results: List[Dict[str, Any]] = []
        with self._lock:
            for (host, port), last_seen in list(self._peers.items()):
                age = now - last_seen
                if age <= self.peer_ttl:
                    results.append(
                        {
                            "host": host,
                            "port": port,
                            "age": age,
                            "is_active": age <= 10.0,
                        }
                    )
        results.sort(key=lambda item: (item["host"], item["port"]))
        return results

    def _run_loop(self):
        # Initial probe broadcast on startup
        self.probe()
        last_probe = time.monotonic()

        while self._running:
            try:
                raw, addr = self.sock.recvfrom(256)
                pkt = unpack_packet(raw)
                if pkt.pkt_type == PacketType.BEACON:
                    data_port = pkt.img_id
                    host = addr[0]
                    with self._lock:
                        self._peers[(host, data_port)] = time.monotonic()
            except (socket.timeout, BlockingIOError):
                pass
            except Exception:
                pass

            now = time.monotonic()
            if now - last_probe >= self.probe_interval:
                self.probe()
                last_probe = now
