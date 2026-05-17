#!/usr/bin/env python3
"""Smoke-test DistilBERT classifier against a running local server."""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

CASES = [
    ("general_chat", "Hey, how are you today?"),
    ("code_generation", "Fix this bug: my React useEffect runs twice."),
    ("summarization", "TL;DR this paragraph about Kubernetes scheduling."),
    ("advanced_chat", "Give a rigorous proof sketch for why P != NP is hard to prove."),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:3011")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    ok = 0
    run_id = int(time.time())
    with httpx.Client(timeout=60.0) as client:
        r = client.get(f"{base}/readyz")
        r.raise_for_status()
        print("ready:", r.json())

        for expected, text in CASES:
            t0 = time.perf_counter()
            resp = client.post(
                f"{base}/classify",
                json={"text": text, "tenant_id": f"smoke-{run_id}"},
            )
            ms = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            got = data.get("intent_label")
            match = got == expected
            ok += int(match)
            status = "OK" if match else "MISS"
            print(
                f"[{status}] expected={expected} got={got} "
                f"conf={data.get('confidence'):.3f} source={data.get('source')} "
                f"latency_ms={ms:.1f}"
            )

        # Cache hit: repeat code_generation prompt
        t0 = time.perf_counter()
        resp2 = client.post(
            f"{base}/classify",
            json={"text": CASES[1][1], "tenant_id": "test"},
        )
        ms2 = (time.perf_counter() - t0) * 1000
        data2 = resp2.json()
        print(
            f"cache repeat: source={data2.get('source')} latency_ms={ms2:.1f} "
            f"payload={json.dumps(data2)}"
        )

    print(f"\n{ok}/{len(CASES)} routing matches")
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
