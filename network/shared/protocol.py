"""
Smoke Alert Protocol (SAP) - Shared Protocol Definitions
Course: Network Programming (LTM)
Specification: prompt/smoke-alert-protocol-spec.md
"""

from __future__ import annotations
import socket
import struct
import sys
import zlib
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple, Union

# Ensure stdout uses UTF-8 where possible on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def safe_print(msg: str):
    """Safely prints message avoiding Windows console encoding crashes."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or "utf-8"
            clean_msg = msg.encode(encoding, errors="replace").decode(encoding)
            print(clean_msg, flush=True)
        except Exception:
            pass

# Network byte order (big-endian), no padding
# magic(4s), type(B), img_id(I), seq(H), total(H), payload_len(H), crc32(I)
HEADER_FORMAT = "!4sBIHHHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 19 bytes

MAGIC = b"SAP1"

class PacketType:
    META = 1   # Announces an incoming image transfer
    CHUNK = 2  # One fragment of image data
    ACK = 3    # Receiver confirms full image reassembled + CRC verified
    NACK = 4   # Receiver requests retransmission of specific seq numbers

    @classmethod
    def name(cls, ptype: int) -> str:
        names = {cls.META: "META", cls.CHUNK: "CHUNK", cls.ACK: "ACK", cls.NACK: "NACK"}
        return names.get(ptype, f"UNKNOWN({ptype})")

# Safe UDP payload limit to avoid IP fragmentation (1400B payload + 19B header = 1419B <= 1472B)
MAX_PAYLOAD = 1400

@dataclass
class Packet:
    magic: bytes
    pkt_type: int
    img_id: int
    seq: int
    total: int
    payload_len: int
    crc32: int
    payload: bytes

    @property
    def is_meta(self) -> bool:
        return self.pkt_type == PacketType.META

    @property
    def is_chunk(self) -> bool:
        return self.pkt_type == PacketType.CHUNK

    @property
    def is_ack(self) -> bool:
        return self.pkt_type == PacketType.ACK

    @property
    def is_nack(self) -> bool:
        return self.pkt_type == PacketType.NACK


def compute_crc32(data: bytes) -> int:
    """Computes standard unsigned 32-bit CRC32 checksum."""
    return zlib.crc32(data) & 0xFFFFFFFF


def pack_packet(
    pkt_type: int,
    img_id: int,
    seq: int,
    total: int,
    crc32: int,
    payload: bytes = b"",
) -> bytes:
    """Serializes a protocol packet into raw bytes with standard 19-byte header."""
    payload_len = len(payload)
    if payload_len > 65535:
        raise ValueError(f"Payload size ({payload_len}) exceeds 16-bit max size (65535)")
    header = struct.pack(HEADER_FORMAT, MAGIC, pkt_type, img_id, seq, total, payload_len, crc32)
    return header + payload


def unpack_packet(raw: bytes) -> Packet:
    """
    Parses raw UDP packet bytes into a Packet object.
    Validates magic bytes and payload length consistency.
    """
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"Packet too short: {len(raw)} bytes (minimum {HEADER_SIZE})")

    magic, pkt_type, img_id, seq, total, payload_len, crc32 = struct.unpack(
        HEADER_FORMAT, raw[:HEADER_SIZE]
    )

    if magic != MAGIC:
        raise ValueError(f"Invalid magic header: {magic!r}, expected {MAGIC!r}")

    payload = raw[HEADER_SIZE : HEADER_SIZE + payload_len]
    if len(payload) != payload_len:
        raise ValueError(
            f"Payload length mismatch: expected {payload_len} bytes, got {len(payload)}"
        )

    return Packet(
        magic=magic,
        pkt_type=pkt_type,
        img_id=img_id,
        seq=seq,
        total=total,
        payload_len=payload_len,
        crc32=crc32,
        payload=payload,
    )


def pack_nack_payload(missing_seqs: Iterable[int]) -> bytes:
    """Packs a list of missing chunk sequence numbers into bytes (2-byte unsigned short each)."""
    seqs = list(missing_seqs)
    return struct.pack(f"!{len(seqs)}H", *seqs)


def unpack_nack_payload(payload: bytes) -> List[int]:
    """Unpacks a byte array of 2-byte sequence numbers from a NACK packet."""
    count = len(payload) // 2
    if count == 0:
        return []
    return list(struct.unpack(f"!{count}H", payload[: count * 2]))


def split_into_chunks(data: bytes, chunk_size: int = MAX_PAYLOAD) -> List[bytes]:
    """Splits byte array into fixed-size chunks of at most chunk_size."""
    if not data:
        return [b""]
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


# -------------------------------------------------------------------------
# Network Utilities (Standard socket only, no extra dependencies)
# -------------------------------------------------------------------------

def get_local_ipv4_addresses() -> List[str]:
    """
    Discovers all non-loopback IPv4 addresses bound to local network interfaces.
    Uses socket only to remain zero-dependency.
    """
    ips = set()
    try:
        hostname = socket.gethostname()
        _, _, addr_list = socket.gethostbyname_ex(hostname)
        for ip in addr_list:
            if ":" not in ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass

    try:
        # UDP dummy connect to discover default gateway route outbound IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            outbound = s.getsockname()[0]
            if outbound and not outbound.startswith("127."):
                ips.add(outbound)
    except Exception:
        pass

    res = sorted(list(ips))
    return res if res else ["127.0.0.1"]


def parse_endpoints(
    raw_endpoints: Union[str, Iterable[str]], default_port: int = 5005
) -> List[Tuple[str, int]]:
    """
    Parses endpoint strings into validated (host, port) tuples.
    Accepts:
      - String: "192.168.1.10:5005, 192.168.1.20:5005" or "192.168.1.10:5005"
      - List/Iterable of strings: ["192.168.1.10:5005", "192.168.1.20"]
    Raises ValueError with descriptive message upon invalid host or port.
    """
    if isinstance(raw_endpoints, str):
        # Split by comma or whitespace
        parts = [p.strip() for p in raw_endpoints.replace(",", " ").split() if p.strip()]
    else:
        parts = []
        for item in raw_endpoints:
            if isinstance(item, str):
                parts.extend([p.strip() for p in item.replace(",", " ").split() if p.strip()])
            elif isinstance(item, tuple) and len(item) == 2:
                parts.append(f"{item[0]}:{item[1]}")

    if not parts:
        raise ValueError("No receiver endpoints specified.")

    results: List[Tuple[str, int]] = []
    for ep in parts:
        if ":" in ep:
            host_part, port_part = ep.rsplit(":", 1)
            host = host_part.strip()
            if not host:
                raise ValueError(f"Invalid endpoint '{ep}': Host cannot be empty.")
            try:
                port = int(port_part.strip())
            except ValueError:
                raise ValueError(f"Invalid endpoint '{ep}': Port '{port_part}' is not an integer.")
        else:
            host = ep.strip()
            port = default_port

        if not (1 <= port <= 65535):
            raise ValueError(f"Invalid port {port} in '{ep}': Must be between 1 and 65535.")

        target = (host, port)
        if target not in results:
            results.append(target)

    return results


# -------------------------------------------------------------------------
# Structured Human-Readable Logging (Per Section 5 of Specification)
# -------------------------------------------------------------------------

LogCallback = Callable[[str], None]


def format_peer_tag(peer: Optional[Union[Tuple[str, int], str]], direction: str = "->") -> str:
    """Formats peer tag maintaining column alignment (e.g. '-> 192.168.1.20:5005 ')."""
    if not peer:
        return ""
    if isinstance(peer, (tuple, list)):
        raw = f"{direction} {peer[0]}:{peer[1]}"
    else:
        s = str(peer).strip()
        raw = s if s.startswith(("->", "<-")) else f"{direction} {s}"
    return f"{raw:<24}"


def format_missing_seqs(missing: Iterable[int], max_items: int = 8) -> str:
    """Formats missing sequences with zero-padded 3-digit numbers."""
    items = list(missing)
    if not items:
        return "[]"
    if len(items) <= max_items:
        formatted = ",".join(f"{s:03d}" for s in items)
        return f"[{formatted}]"
    head = ",".join(f"{s:03d}" for s in items[:max_items])
    return f"[{head},...(+{len(items)-max_items})]"


def log_send_meta(
    img_id: int,
    total: int,
    crc: int,
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    peer_tag = format_peer_tag(peer, "->")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[SEND] META   {gap}img_id={img_id:<5} total={total:<4} crc=0x{crc:08x}"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_send_chunk(
    img_id: int,
    seq: int,
    total: int,
    size: int,
    crc: int,
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    peer_tag = format_peer_tag(peer, "->")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[SEND] CHUNK  {gap}img_id={img_id:<5} seq={seq:03d}/{total:<3} size={size:<5}B crc=0x{crc:08x}"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_recv_chunk(
    img_id: int,
    seq: int,
    total: int,
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    peer_tag = format_peer_tag(peer, "<-")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[RECV] CHUNK  {gap}img_id={img_id:<5} seq={seq:03d}/{total:<3} [OK]"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_drop_chunk(
    img_id: int,
    seq: int,
    total: int,
    reason: str,
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    peer_tag = format_peer_tag(peer, "<-")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[DROP] CHUNK  {gap}img_id={img_id:<5} seq={seq:03d}/{total:<3} ({reason})"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_send_nack(
    img_id: int,
    missing: Iterable[int],
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    missing_str = format_missing_seqs(missing)
    peer_tag = format_peer_tag(peer, "->")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[SEND] NACK   {gap}img_id={img_id:<5} missing={missing_str}"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_recv_nack(
    img_id: int,
    missing: Iterable[int],
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    missing_str = format_missing_seqs(missing)
    peer_tag = format_peer_tag(peer, "<-")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[RECV] NACK   {gap}img_id={img_id:<5} missing={missing_str} -> retransmitting"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_send_ack(
    img_id: int,
    total: int,
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    peer_tag = format_peer_tag(peer, "->")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[SEND] ACK    {gap}img_id={img_id:<5} -- transfer complete ({total}/{total})"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_recv_ack(
    img_id: int,
    total: int,
    rounds: int,
    callback: Optional[LogCallback] = None,
    peer: Optional[Union[Tuple[str, int], str]] = None,
) -> str:
    round_text = "round" if rounds == 1 else "rounds"
    peer_tag = format_peer_tag(peer, "<-")
    gap = f"{peer_tag} " if peer_tag else ""
    line = f"[RECV] ACK    {gap}img_id={img_id:<5} -- transfer complete ({total}/{total}, {rounds} retransmit {round_text})"
    safe_print(line)
    if callback:
        callback(line)
    return line


def log_info(msg: str, callback: Optional[LogCallback] = None) -> str:
    line = f"[INFO] {msg}"
    safe_print(line)
    if callback:
        callback(line)
    return line
