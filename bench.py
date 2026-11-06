r"""Microbenchmarks of the defence primitives (RUNBOOK Phase 3, step 5).

Measures, in microseconds (median and 95th percentile over N repetitions):
TOTP code, TOTP verify, a full D1 handshake (4 messages, in-process), Ed25519 sign,
Ed25519 verify, a full D2 verify_incoming, and a full monitor check.
Usage: .\.venv\Scripts\python.exe bench.py [--n 10000]   -> tables/bench.csv
"""
from __future__ import annotations

import argparse
import csv
import platform
import statistics
import tempfile
import time
from pathlib import Path
from random import Random

from bus import Accept, Bus
from clock import SimClock
from config import ROOT, load_config
from defences import make_defence
from defences.base import PaymentRequest
from message import AGENTS, Message, canonical_bytes, new_msg_id
from runlog import RunLogger
from world import World


def timeit(fn, n: int) -> list[float]:
    out = []
    for _ in range(n):
        t = time.perf_counter_ns()
        fn()
        out.append((time.perf_counter_ns() - t) / 1000.0)
    return out


def env(name: str, cfg, tmp: Path):
    rng = Random(1)
    clock = SimClock(1_794_000_000_000, real_time=False)
    log = RunLogger(None, "bench", clock)
    world = World(clock, None)
    d = make_defence(name)
    d.setup(world, clock, rng, list(AGENTS), cfg, log)
    bus = Bus(clock, d, log, rng)
    bus.register_endpoint("finance", lambda m, v: Message(new_msg_id(rng), "finance", m.sender, clock.now_ms(),
                                                          m.task_id, {"kind": "payment_result", "status": "paid",
                                                                      "invoice_id": "INV-104", "detail": ""}))
    return rng, clock, log, world, d, bus


def pay(rng, clock) -> Message:
    return Message(new_msg_id(rng), "orchestrator", "finance", clock.now_ms(), "T-1",
                   {"kind": "pay_invoice", "invoice_id": "INV-104", "supplier": "Acme Ltd",
                    "account": "GB-ACME-001", "amount_pence": 120000})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    args = ap.parse_args(argv)
    n = args.n
    cfg = load_config()
    tmp = Path(tempfile.mkdtemp())
    results = []

    rng, clock, log, world, d1, bus1 = env("D1", cfg, tmp)
    t = clock.now_ms()
    code = d1.code_c(t)
    results.append(("totp_code", timeit(lambda: d1.code_c(t), n)))
    results.append(("totp_verify_window1", timeit(lambda: d1.check_c(code, t), n)))

    def handshake():
        d1.end_task()
        d1._handshake("orchestrator", "finance", "T-1", bus1)
    results.append(("d1_full_handshake_4_messages", timeit(handshake, max(n // 10, 100))))

    rng, clock, log, world, d2, bus2 = env("D2", cfg, tmp)
    key = d2.keys["orchestrator"]
    m = d2.sign_with(pay(rng, clock), key)
    data = canonical_bytes(m, ("alg", "nonce", "ts_ms"))
    sig = key.sign(data)
    pub = key.public_key()
    results.append(("ed25519_sign", timeit(lambda: key.sign(data), n)))
    results.append(("ed25519_verify", timeit(lambda: pub.verify(sig, data), n)))

    def d2_verify():
        msg = d2.sign_with(pay(rng, clock), key)
        d2.verify_incoming(msg, "finance")
    results.append(("d2_sign_plus_full_verify_K1_K6", timeit(d2_verify, n)))

    rng, clock, log, world, d3, bus3 = env("D3", cfg, tmp)
    world.register_task("T-1", "INV-104")
    trig = d3.sign_with(pay(rng, clock), d3.keys["orchestrator"])
    req = PaymentRequest("INV-104", "GB-ACME-001", 120000)
    results.append(("monitor_full_check_R1_R4", timeit(lambda: d3.payment_gate(req, trig, Accept("orchestrator", "verified")), n)))

    out = ROOT / "tables" / "bench.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["primitive", "n", "median_us", "p95_us", "mean_us", "machine"])
        machine = f"{platform.processor() or platform.machine()} | {platform.system()} {platform.release()} | Python {platform.python_version()}"
        for name, xs in results:
            xs_sorted = sorted(xs)
            p95 = xs_sorted[int(0.95 * (len(xs_sorted) - 1))]
            w.writerow([name, len(xs), round(statistics.median(xs), 2), round(p95, 2), round(statistics.fmean(xs), 2), machine])
            print(f"{name:34s} n={len(xs):6d} median={statistics.median(xs):9.2f} us  p95={p95:9.2f} us")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
