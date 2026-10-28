"""
Smoke Alert Protocol (SAP) - Protocol Performance Benchmark
Specification: prompt/prompt-agent-protocol-benchmark.md
Course: Network Programming (LTM)

Measures protocol reliability overhead (latency, NACK retransmission rounds, success rate)
under controlled Bernoulli packet loss using an in-process socket-level fault injector.

Usage:
    python -m network.tests.benchmark_performance
or
    python network/tests/benchmark_performance.py
"""

import csv
import math
import os
from pathlib import Path
import random
import socket
import sys
import time
from typing import Dict, List, Optional, Tuple

# Ensure project root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure UTF-8 output encoding on Windows console
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from network.shared.protocol import (
    MAX_PAYLOAD,
    PacketType,
    compute_crc32,
    pack_packet,
    unpack_packet,
)
from network.sender.sender import SmokeAlertSender
from network.receiver.receiver import SmokeAlertReceiver

# Configuration parameters
LOSS_RATES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
TRIALS_PER_RATE = 30
BASE_PORT = 5800
CSV_OUTPUT_PATH = BASE_DIR / "network" / "tests" / "benchmark_results.csv"


class ProbabilisticFaultSocket:
    """
    Socket wrapper that simulates packet loss at a designated loss rate using a seeded PRNG.
    Specifically drops CHUNK packets on the sender side to benchmark selective NACK retransmission.
    Also tracks NACK packet arrivals to record retransmission rounds.
    """

    def __init__(self, real_sock: socket.socket, loss_rate: float = 0.0, seed: int = 42):
        self._sock = real_sock
        self.loss_rate = loss_rate
        self.rng = random.Random(seed)
        self.nack_rounds = 0
        self.chunks_sent = 0
        self.chunks_dropped = 0

    def __getattr__(self, name):
        return getattr(self._sock, name)

    def sendto(self, data: bytes, addr) -> int:
        try:
            pkt = unpack_packet(data)
            # Only subject data CHUNK packets to stochastic loss
            if pkt.is_chunk:
                self.chunks_sent += 1
                if self.loss_rate > 0.0 and self.rng.random() < self.loss_rate:
                    self.chunks_dropped += 1
                    # Silently drop packet by returning byte count without forwarding to socket
                    return len(data)
        except Exception:
            pass
        return self._sock.sendto(data, addr)

    def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
        data, addr = self._sock.recvfrom(bufsize)
        try:
            pkt = unpack_packet(data)
            if pkt.is_nack:
                self.nack_rounds += 1
        except Exception:
            pass
        return data, addr


def load_or_create_benchmark_image() -> bytes:
    """
    Loads a realistic sample JPEG image (~40-60KB) from the dataset,
    or generates a synthetic JPEG of equivalent size if dataset is absent.
    """
    # 1. Try finding a real dataset test image
    test_img_dir = BASE_DIR / "model" / "dataset" / "images" / "test"
    if test_img_dir.exists():
        jpgs = sorted(list(test_img_dir.glob("*.jpg")))
        if jpgs:
            # Pick a representative image around median size (~40-50KB)
            for candidate in jpgs:
                data = candidate.read_bytes()
                if 30_000 <= len(data) <= 65_000:
                    return data
            return jpgs[0].read_bytes()

    # 2. Fallback: generate synthetic image pattern (~42KB, 30 chunks)
    size = 30 * MAX_PAYLOAD - 200
    pattern = b"SAP_BENCHMARK_SYNTHETIC_FRAME_HEADER_PAYLOAD_" * (size // 45 + 1)
    return pattern[:size]


def run_benchmark():
    image_bytes = load_or_create_benchmark_image()
    image_size_kb = len(image_bytes) / 1024.0
    total_chunks = math.ceil(len(image_bytes) / MAX_PAYLOAD)

    print("=" * 80)
    print("      SMOKE ALERT PROTOCOL (SAP) - PERFORMANCE & RELIABILITY BENCHMARK")
    print("=" * 80)
    print(f"Benchmark Image Size: {len(image_bytes):,} bytes ({image_size_kb:.2f} KB, {total_chunks} SAP chunks)")
    print(f"Evaluated Loss Rates: {[f'{int(r*100)}%' for r in LOSS_RATES]}")
    print(f"Trials per Condition: {TRIALS_PER_RATE} independent runs (N={TRIALS_PER_RATE*len(LOSS_RATES)} total)")
    print(f"Sender Wait Timeout:  0.50 s (500 ms)")
    print(f"Receiver Inactivity:  0.30 s (300 ms)")
    print(f"Max Retry Limit:      5 retries")
    print("-" * 80)

    # Disable protocol debug logs during benchmark to maintain clean output and maximum timing fidelity
    quiet_logger = lambda msg: None

    benchmark_rows = []

    for rate_idx, loss_rate in enumerate(LOSS_RATES):
        loss_pct_str = f"{int(loss_rate * 100)}%"
        print(f"\n[{rate_idx+1}/{len(LOSS_RATES)}] Benchmarking Loss Rate: {loss_pct_str} ({TRIALS_PER_RATE} trials)...", flush=True)

        trial_latencies = []
        trial_nack_rounds = []
        trial_successes = []

        # Run trials for this loss rate
        for trial in range(TRIALS_PER_RATE):
            # Unique deterministic seed per trial to prevent sampling bias
            seed = 1000 * int(loss_rate * 100) + trial + 1
            port = BASE_PORT + (trial % 20)
            img_id = 10_000 + (rate_idx * 100) + trial

            received_data = {}

            def on_recv(i_id, data, ts):
                received_data[i_id] = data

            # Initialize in-process receiver on loopback
            receiver = SmokeAlertReceiver(
                listen_host="127.0.0.1",
                listen_port=port,
                inactivity_timeout=0.3,
                max_retries=5,
                enable_discovery=False,
                on_image_received=on_recv,
                log_callback=quiet_logger,
            )
            receiver.start()

            # Initialize sender with wrapped fault socket
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            raw_sock.settimeout(0.5)
            fault_sock = ProbabilisticFaultSocket(real_sock=raw_sock, loss_rate=loss_rate, seed=seed)

            sender = SmokeAlertSender(
                target_host="127.0.0.1",
                target_port=port,
                wait_timeout=0.5,
                max_retries=5,
                sock=fault_sock,
                log_callback=quiet_logger,
            )

            # Measure transfer time with monotonic high-resolution timer
            t_start = time.perf_counter()
            success = sender.send_image(
                img_id=img_id,
                image_bytes=image_bytes,
                timestamp_str=f"bench_loss_{loss_rate:.2f}_t_{trial}",
            )
            t_end = time.perf_counter()

            sender.close()
            receiver.stop()

            latency_ms = (t_end - t_start) * 1000.0

            # Verify byte-for-byte fidelity and CRC32 on successful runs
            is_valid_success = (
                success
                and (img_id in received_data)
                and (received_data[img_id] == image_bytes)
                and (compute_crc32(received_data[img_id]) == compute_crc32(image_bytes))
            )

            trial_latencies.append(latency_ms)
            trial_nack_rounds.append(fault_sock.nack_rounds)
            trial_successes.append(1 if is_valid_success else 0)

        # Compute aggregate metrics
        mean_latency = sum(trial_latencies) / len(trial_latencies)
        variance = sum((x - mean_latency) ** 2 for x in trial_latencies) / len(trial_latencies)
        std_latency = math.sqrt(variance)
        mean_nacks = sum(trial_nack_rounds) / len(trial_nack_rounds)
        success_rate = (sum(trial_successes) / len(trial_successes)) * 100.0

        benchmark_rows.append({
            "loss_rate": loss_pct_str,
            "loss_val": loss_rate,
            "mean_latency_ms": mean_latency,
            "std_latency_ms": std_latency,
            "mean_nack_rounds": mean_nacks,
            "success_rate_pct": success_rate,
        })

        print(
            f"   -> Latency: {mean_latency:6.2f} ms (±{std_latency:5.2f} ms) | "
            f"NACK Rounds: {mean_nacks:4.2f} | "
            f"Success: {success_rate:5.1f}%"
        )

    # Write results to CSV
    CSV_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["loss_rate", "mean_latency_ms", "std_latency_ms", "mean_nack_rounds", "success_rate_pct"])
        for r in benchmark_rows:
            writer.writerow([
                r["loss_rate"],
                f"{r['mean_latency_ms']:.2f}",
                f"{r['std_latency_ms']:.2f}",
                f"{r['mean_nack_rounds']:.2f}",
                f"{r['success_rate_pct']:.1f}%",
            ])
    print(f"\n[OK] CSV benchmark results exported to: {CSV_OUTPUT_PATH}")

    # Build Markdown table ready for report Table 4.4
    md_lines = [
        "| Tỉ lệ mất gói | Latency TB (ms) | Độ lệch chuẩn | Số round NACK TB | Tỉ lệ thành công |",
        "|---|---|---|---|---|",
    ]
    for r in benchmark_rows:
        md_lines.append(
            f"| {r['loss_rate']} | {r['mean_latency_ms']:.1f} ms | ±{r['std_latency_ms']:.1f} ms | "
            f"{r['mean_nack_rounds']:.2f} | {r['success_rate_pct']:.1f}% |"
        )

    md_table = "\n".join(md_lines)

    print("\n" + "=" * 32 + " BẢNG 4.4 SẴN SÀNG DÁN VÀO BÁO CÁO " + "=" * 32)
    print(md_table)
    print("=" * 96)
    print(
        "\n> [!NOTE]\n"
        "> *\"Số liệu đo bằng benchmark_performance.py trên môi trường fault-injection\n"
        "> tất định (loopback, in-process, N=30 trial/mức), phản ánh overhead của cơ chế\n"
        "> reliability ở tầng giao thức SAP. Không đại diện cho độ trễ mạng LAN vật lý thật.\"*\n"
    )

    return benchmark_rows


if __name__ == "__main__":
    run_benchmark()
