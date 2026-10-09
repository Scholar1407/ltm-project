"""
Smoke Alert Protocol (SAP) - Sender Implementation
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md Section 3 & Section 5
"""

from __future__ import annotations
import math
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Support both relative and absolute imports
try:
    from ..shared.protocol import (
        HEADER_SIZE,
        MAX_PAYLOAD,
        Packet,
        PacketType,
        compute_crc32,
        log_drop_chunk,
        log_info,
        log_recv_ack,
        log_recv_nack,
        log_send_chunk,
        log_send_meta,
        pack_packet,
        parse_endpoints,
        split_into_chunks,
        unpack_nack_payload,
        unpack_packet,
    )
except (ImportError, ValueError):
    from network.shared.protocol import (
        HEADER_SIZE,
        MAX_PAYLOAD,
        Packet,
        PacketType,
        compute_crc32,
        log_drop_chunk,
        log_info,
        log_recv_ack,
        log_recv_nack,
        log_send_chunk,
        log_send_meta,
        pack_packet,
        parse_endpoints,
        split_into_chunks,
        unpack_nack_payload,
        unpack_packet,
    )


class SmokeAlertSender:
    """
    Sends detected smoking alert images over raw UDP using the Smoke Alert Protocol (SAP).
    Implements reliable chunked transmission with NACK-based selective retransmission.
    Supports single or multiple receiver endpoints via one-socket-per-receiver independent workers.
    """

    def __init__(
        self,
        target_host: str = "127.0.0.1",
        target_port: int = 5005,
        receivers: Optional[Union[str, List[Tuple[str, int]], List[str]]] = None,
        wait_timeout: float = 0.5,  # 500ms wait window per spec
        max_retries: int = 5,
        sock: Optional[socket.socket] = None,
        sock_factory: Optional[Callable[[Tuple[str, int]], socket.socket]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        if receivers:
            if isinstance(receivers, (str, list)) and not (
                isinstance(receivers, list)
                and receivers
                and isinstance(receivers[0], tuple)
            ):
                self.receivers = parse_endpoints(receivers, default_port=target_port)
            else:
                self.receivers = list(receivers)  # list of (host, port)
        else:
            self.receivers = [(target_host, target_port)]

        # Maintain single-target backward compatibility attributes
        self.target_host = self.receivers[0][0]
        self.target_port = self.receivers[0][1]
        self.target_addr = self.receivers[0]

        self.wait_timeout = wait_timeout
        self.max_retries = max_retries
        self.sock = sock
        self.sock_factory = sock_factory
        self.log_callback = log_callback
        self.last_results: Dict[Tuple[str, int], bool] = {}

        self._own_socket = sock is None
        if sock is not None:
            self.sock = sock
        elif len(self.receivers) == 1 and not sock_factory:
            # Pre-create default socket for single receiver
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(self.wait_timeout)
        else:
            self.sock = None

    def close(self):
        """Closes the underlying socket if owned by this sender."""
        if self._own_socket and self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _send_to_receiver(
        self,
        target_addr: Tuple[str, int],
        img_id: int,
        chunks: List[bytes],
        chunk_crcs: List[int],
        whole_crc: int,
        meta_pkt: bytes,
        sock: socket.socket,
        own_sock: bool,
    ) -> bool:
        """
        Executes the Section 3 state machine against a single receiver endpoint
        using a dedicated UDP socket. Independent from other receivers.
        """
        total_chunks = len(chunks)
        try:
            # 1. Send META packet
            sock.sendto(meta_pkt, target_addr)
            log_send_meta(img_id, total_chunks, whole_crc, self.log_callback, peer=target_addr)

            # 2. Send all CHUNK packets in sequence (seq 0 .. total-1)
            for seq, chunk_data in enumerate(chunks):
                chunk_crc = chunk_crcs[seq]
                pkt = pack_packet(
                    pkt_type=PacketType.CHUNK,
                    img_id=img_id,
                    seq=seq,
                    total=total_chunks,
                    crc32=chunk_crc,
                    payload=chunk_data,
                )
                sock.sendto(pkt, target_addr)
                log_send_chunk(
                    img_id,
                    seq,
                    total_chunks,
                    len(chunk_data),
                    chunk_crc,
                    self.log_callback,
                    peer=target_addr,
                )

            # 3. State machine: wait for ACK / NACK with timeout window
            retries = 0
            retransmit_rounds = 0
            sock.settimeout(self.wait_timeout)

            while retries <= self.max_retries:
                try:
                    raw_data, addr = sock.recvfrom(65535)
                    packet = unpack_packet(raw_data)

                    # Ignore packets for different image transfers
                    if packet.img_id != img_id:
                        continue

                    if packet.is_ack:
                        log_recv_ack(
                            img_id,
                            total_chunks,
                            retransmit_rounds,
                            self.log_callback,
                            peer=target_addr,
                        )
                        return True

                    elif packet.is_nack:
                        missing_seqs = unpack_nack_payload(packet.payload)
                        log_recv_nack(img_id, missing_seqs, self.log_callback, peer=target_addr)
                        retransmit_rounds += 1

                        # Resend only the missing chunks requested by receiver
                        for seq in missing_seqs:
                            if 0 <= seq < total_chunks:
                                chunk_data = chunks[seq]
                                chunk_crc = chunk_crcs[seq]
                                pkt = pack_packet(
                                    pkt_type=PacketType.CHUNK,
                                    img_id=img_id,
                                    seq=seq,
                                    total=total_chunks,
                                    crc32=chunk_crc,
                                    payload=chunk_data,
                                    )
                                sock.sendto(pkt, target_addr)
                                log_send_chunk(
                                    img_id,
                                    seq,
                                    total_chunks,
                                    len(chunk_data),
                                    chunk_crc,
                                    self.log_callback,
                                    peer=target_addr,
                                )

                        # Reset timeout window after retransmitting
                        sock.settimeout(self.wait_timeout)

                except socket.timeout:
                    retries += 1
                    if retries > self.max_retries:
                        break

                    log_info(
                        f"Wait window expired for img_id={img_id} to {target_addr[0]}:{target_addr[1]} (retry {retries}/{self.max_retries}). Re-announcing META...",
                        self.log_callback,
                    )
                    sock.sendto(meta_pkt, target_addr)
                    sock.settimeout(self.wait_timeout)

                except Exception as e:
                    log_info(
                        f"Unexpected error in sender loop to {target_addr}: {e}",
                        self.log_callback,
                    )

            log_info(
                f"[FAIL] img_id={img_id} -> {target_addr[0]}:{target_addr[1]} max retries ({self.max_retries}) exhausted without ACK. Abandoning transfer.",
                self.log_callback,
            )
            return False
        finally:
            if own_sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def send_image(
        self,
        img_id: int,
        image_bytes: bytes,
        timestamp_str: str = "",
    ) -> bool:
        """
        Transmits the same image to ALL configured receivers concurrently.
        Each receiver is served by an independent worker running on its own UDP socket.
        Returns True if at least one receiver acknowledged completion, False if all failed.
        """
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty")

        # 1. Compute whole-image CRC32 & split into chunks
        whole_crc = compute_crc32(image_bytes)
        chunks: List[bytes] = split_into_chunks(image_bytes, MAX_PAYLOAD)
        total_chunks = len(chunks)
        chunk_crcs = [compute_crc32(c) for c in chunks]

        # 2. Build META packet once for all receivers
        meta_payload = timestamp_str.encode("utf-8") if timestamp_str else b""
        meta_pkt = pack_packet(
            pkt_type=PacketType.META,
            img_id=img_id,
            seq=0,
            total=total_chunks,
            crc32=whole_crc,
            payload=meta_payload,
        )

        # 3. Single-receiver optimization with pre-existing socket (preserves exact test semantics)
        if len(self.receivers) == 1 and self.sock is not None and not self.sock_factory:
            ok = self._send_to_receiver(
                self.receivers[0],
                img_id,
                chunks,
                chunk_crcs,
                whole_crc,
                meta_pkt,
                self.sock,
                own_sock=False,
            )
            self.last_results = {self.receivers[0]: ok}
            return ok

        # 4. Multi-receiver fan-out: 1 UDP socket per receiver, 1 worker per receiver
        threads: List[threading.Thread] = []
        results: Dict[Tuple[str, int], bool] = {}
        lock = threading.Lock()

        for target_addr in self.receivers:
            if self.sock_factory:
                s = self.sock_factory(target_addr)
                own = False
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(self.wait_timeout)
                own = True

            def worker(target=target_addr, worker_sock=s, is_own=own):
                res = self._send_to_receiver(
                    target,
                    img_id,
                    chunks,
                    chunk_crcs,
                    whole_crc,
                    meta_pkt,
                    worker_sock,
                    is_own,
                )
                with lock:
                    results[target] = res

            t = threading.Thread(target=worker, daemon=True)
            threads.append(t)
            t.start()

        # Wait for all independent receiver transfers to finish
        for t in threads:
            t.join()

        self.last_results = results
        return any(results.values()) if results else False


if __name__ == "__main__":
    import argparse
    import cv2
    import numpy as np

    parser = argparse.ArgumentParser(description="SAP Smoke Alert Protocol Sender CLI")
    parser.add_argument("--host", default="127.0.0.1", help="Default receiver IP address")
    parser.add_argument("--port", type=int, default=5005, help="Default receiver UDP port")
    parser.add_argument(
        "--receivers",
        nargs="*",
        default=None,
        help="List of receiver endpoints (e.g. --receivers 127.0.0.1:5005 192.168.1.20:5005)",
    )
    parser.add_argument("--image", default="", help="Path to test image file (optional)")
    args = parser.parse_args()

    # Determine endpoints
    endpoints = args.receivers if args.receivers else [f"{args.host}:{args.port}"]

    # Create or load image
    if args.image and Path(args.image).exists():
        with open(args.image, "rb") as f:
            img_bytes = f.read()
    else:
        # Create synthetic test alert image with OpenCV
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        test_frame[:] = (30, 30, 30)
        cv2.putText(
            test_frame,
            "TEST SMOKING ALERT (SAP DEMO)",
            (50, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
        )
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            test_frame,
            f"TIMESTAMP: {t_str}",
            (50, 260),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        _, enc = cv2.imencode(".jpg", test_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        img_bytes = enc.tobytes()

    sender = SmokeAlertSender(receivers=endpoints)
    test_id = int(time.time()) % 10000
    print(f"Starting test send: img_id={test_id}, payload_size={len(img_bytes)}B to {sender.receivers}")
    success = sender.send_image(test_id, img_bytes, time.strftime("%Y-%m-%d %H:%M:%S"))
    sender.close()
    print(f"Overall Result: {'SUCCESS' if success else 'FAILED'} -> Details: {sender.last_results}")
