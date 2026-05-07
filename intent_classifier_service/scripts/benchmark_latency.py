#!/usr/bin/env python3
"""HTTP latency benchmark with separate cache-hit and model-path gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import httpx


def percentile(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return 0.0
    k = (len(sorted_ms) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(sorted_ms) - 1)
    if f == c:
        return sorted_ms[f]
    return sorted_ms[f] + (sorted_ms[c] - sorted_ms[f]) * (k - f)


async def main_async() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3010")
    ap.add_argument("--text", default="Summarize this in one line: machine learning is useful.")
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--max-p95-ms", type=float, default=100.0)
    vary_group = ap.add_mutually_exclusive_group()
    vary_group.add_argument("--vary-text", dest="vary_text", action="store_true")
    vary_group.add_argument("--no-vary-text", dest="vary_text", action="store_false")
    ap.set_defaults(vary_text=True)
    args = ap.parse_args()
    base = args.url.rstrip("/")

    if not args.vary_text:
        print("WARNING: This benchmark does not reflect LLM inference latency.")
        print("Run with --vary-text for a real SLO measurement.")

    async def run_gate(*, gate_name: str, vary_text: bool) -> dict[str, float]:
        warmup = 20
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(warmup):
                warmup_text = f"{args.text} #warmup{i}" if vary_text else args.text
                r = await client.post(f"{base}/classify", json={"text": warmup_text})
                r.raise_for_status()

            sem = asyncio.Semaphore(args.concurrency)
            latencies: list[float] = []

            async def one(i: int) -> None:
                t = f"{args.text} #{i}" if vary_text else args.text
                payload = {"text": t}
                async with sem:
                    t0 = time.perf_counter()
                    r = await client.post(f"{base}/classify", json=payload)
                    dt = (time.perf_counter() - t0) * 1000.0
                    r.raise_for_status()
                    latencies.append(dt)

            await asyncio.gather(*(one(i) for i in range(args.requests)))

        latencies.sort()
        p50 = percentile(latencies, 50)
        p95 = percentile(latencies, 95)
        p99 = percentile(latencies, 99)
        result = {
            "gate": gate_name,
            "n": len(latencies),
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "concurrency": args.concurrency,
        }
        print(json.dumps(result, indent=2))
        return result

    print("=== cache-hit path ===")
    cache_hit_result = await run_gate(gate_name="cache-hit path", vary_text=False)

    model_result: dict[str, float] | None = None
    if args.vary_text:
        print("\n=== model path ===")
        model_result = await run_gate(gate_name="model path", vary_text=True)

    gate_to_check = model_result or cache_hit_result
    if gate_to_check["p95_ms"] > args.max_p95_ms:
        print(
            f"FAIL: {gate_to_check['gate']} p95 {gate_to_check['p95_ms']:.2f}ms "
            f"> {args.max_p95_ms}ms",
            file=sys.stderr,
        )
        return 1
    print("PASS latency gate")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
