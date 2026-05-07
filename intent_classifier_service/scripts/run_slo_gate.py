#!/usr/bin/env python3
"""Run accuracy (offline) + latency (HTTP) gates for rollout. Exit 0 only if both pass."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser()
    ap.add_argument("--taxonomy", type=Path, default=root / "intent_taxonomy" / "intent_labels_v1.yaml")
    ap.add_argument("--test-set", type=Path, default=root / "intent_classifier_service" / "eval" / "default_test.jsonl")
    ap.add_argument("--classifier-url", default="http://127.0.0.1:3010")
    ap.add_argument("--skip-latency", action="store_true")
    ap.add_argument("--min-accuracy", type=float, default=0.90)
    ap.add_argument("--max-p95-ms", type=float, default=100.0)
    args = ap.parse_args()

    acc_script = root / "intent_classifier_service" / "scripts" / "evaluate_accuracy.py"
    lat_script = root / "intent_classifier_service" / "scripts" / "benchmark_latency.py"

    r1 = subprocess.run(
        [
            sys.executable,
            str(acc_script),
            "--taxonomy",
            str(args.taxonomy),
            "--test-set",
            str(args.test_set),
            "--min-accuracy",
            str(args.min_accuracy),
        ],
        cwd=str(root),
    )
    if r1.returncode != 0:
        return r1.returncode

    if args.skip_latency:
        return 0

    r2 = subprocess.run(
        [
            sys.executable,
            str(lat_script),
            "--url",
            args.classifier_url,
            "--max-p95-ms",
            str(args.max_p95_ms),
        ],
        cwd=str(root),
    )
    return r2.returncode


if __name__ == "__main__":
    raise SystemExit(main())
