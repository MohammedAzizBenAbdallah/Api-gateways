#!/usr/bin/env python3
"""Accuracy eval against intent_classifier_service eval set."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3011")
    ap.add_argument(
        "--jsonl",
        default=str(
            Path(__file__).resolve().parents[2]
            / "intent_classifier_service"
            / "eval"
            / "default_test.jsonl"
        ),
    )
    args = ap.parse_args()
    base = args.url.rstrip("/")
    path = Path(args.jsonl)
    if not path.is_file():
        print(f"Missing eval file: {path}", file=sys.stderr)
        return 1

    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    correct = 0
    latencies: list[float] = []
    with httpx.Client(timeout=60.0) as client:
        for i, row in enumerate(rows):
            text = row["text"]
            expected = row["label"]
            t0 = time.perf_counter()
            r = client.post(
                f"{base}/classify",
                json={"text": f"{text} #{i}", "tenant_id": "eval"},
            )
            ms = (time.perf_counter() - t0) * 1000
            latencies.append(ms)
            r.raise_for_status()
            got = r.json().get("intent_label")
            if got == expected:
                correct += 1

    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    acc = correct / len(rows) if rows else 0
    print(json.dumps({
        "samples": len(rows),
        "accuracy": round(acc, 3),
        "correct": correct,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
    }, indent=2))
    return 0 if acc >= 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
