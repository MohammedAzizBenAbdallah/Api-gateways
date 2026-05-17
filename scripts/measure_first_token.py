#!/usr/bin/env python3
"""Measure chat API TTFB, first SSE event, and first non-empty token latency."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("CHAT_URL", "http://localhost/api/ai/request")
TOKEN = os.environ.get("BEARER_TOKEN", "")
INTENT = os.environ.get("CHAT_INTENT", "auto")
PROMPT = os.environ.get(
    "CHAT_PROMPT", "Say hello in one short sentence."
)


def measure_once() -> dict:
    body = json.dumps(
        {
            "intent": INTENT,
            "payload": {
                "messages": [{"role": "user", "content": PROMPT}]
            },
            "metadata": {"sensitivity": "LOW", "environment": "dev"},
        }
    ).encode()

    req = urllib.request.Request(
        URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "text/event-stream",
            "kong-header": "true",
        },
    )

    t0 = time.perf_counter()
    first_byte_ms = None
    first_event_ms = None
    first_empty_token_ms = None
    first_nonempty_token_ms = None
    first_nonempty_preview = None
    status = None
    error_body = None
    token_chunks = 0
    buffer = b""

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            status = resp.status
            while True:
                chunk = resp.read(1)
                if not chunk:
                    break
                now_ms = (time.perf_counter() - t0) * 1000
                if first_byte_ms is None:
                    first_byte_ms = now_ms
                buffer += chunk
                while b"\n\n" in buffer:
                    event, buffer = buffer.split(b"\n\n", 1)
                    for line in event.split(b"\n"):
                        if not line.startswith(b"data: "):
                            continue
                        try:
                            data = json.loads(line[6:].decode())
                        except json.JSONDecodeError:
                            continue
                        if first_event_ms is None:
                            first_event_ms = now_ms
                        if data.get("error"):
                            return {
                                "ok": False,
                                "http_status": status,
                                "stream_error": data.get("error"),
                                "first_byte_ms": first_byte_ms,
                                "first_event_ms": first_event_ms,
                                "elapsed_ms": now_ms,
                            }
                        if data.get("status") == "thinking":
                            continue
                        tok = data.get("token")
                        if tok is None:
                            continue
                        if tok == "" and first_empty_token_ms is None:
                            first_empty_token_ms = now_ms
                        if tok != "":
                            token_chunks += 1
                            if first_nonempty_token_ms is None:
                                first_nonempty_token_ms = now_ms
                                first_nonempty_preview = tok[:60]
    except urllib.error.HTTPError as e:
        status = e.code
        error_body = e.read().decode(errors="replace")[:800]
    except Exception as e:
        return {"ok": False, "error": str(e)}

    total_ms = (time.perf_counter() - t0) * 1000
    # Product NFR: first SSE event (thinking pulse or token)
    nfr_event_ms = first_event_ms or first_byte_ms
    # Model TTFT: first non-empty token
    model_ttft_ms = first_nonempty_token_ms
    return {
        "ok": status == 200 and first_byte_ms is not None,
        "http_status": status,
        "first_byte_ms": round(first_byte_ms, 1) if first_byte_ms else None,
        "first_event_ms": round(first_event_ms, 1) if first_event_ms else None,
        "first_empty_token_ms": round(first_empty_token_ms, 1)
        if first_empty_token_ms
        else None,
        "first_nonempty_token_ms": round(first_nonempty_token_ms, 1)
        if first_nonempty_token_ms
        else None,
        "total_ms": round(total_ms, 1),
        "token_chunks": token_chunks,
        "first_token_preview": first_nonempty_preview,
        "nfr_first_event_under_3s": nfr_event_ms is not None and nfr_event_ms < 3000,
        "nfr_first_event_ms": round(nfr_event_ms, 1) if nfr_event_ms else None,
        "nfr_first_token_under_3s": model_ttft_ms is not None and model_ttft_ms < 3000,
        "nfr_measured_ms": round(model_ttft_ms, 1) if model_ttft_ms else None,
        "error_body": error_body,
    }


def main() -> int:
    if not TOKEN:
        print("BEARER_TOKEN required", file=sys.stderr)
        return 1
    runs = int(os.environ.get("RUNS", "3"))
    results = [measure_once() for _ in range(runs)]
    summary = {
        "url": URL,
        "intent": INTENT,
        "runs": runs,
        "results": results,
    }
    ok_runs = [r for r in results if r.get("ok")]
    if ok_runs:
        event_vals = [
            r.get("nfr_first_event_ms")
            for r in ok_runs
            if r.get("nfr_first_event_ms") is not None
        ]
        model_vals = [
            r.get("nfr_measured_ms")
            for r in ok_runs
            if r.get("nfr_measured_ms") is not None
        ]
        summary["summary"] = {
            "successful_runs": len(ok_runs),
            "first_event_ms_min": min(event_vals) if event_vals else None,
            "first_event_ms_max": max(event_vals) if event_vals else None,
            "first_event_ms_avg": round(sum(event_vals) / len(event_vals), 1)
            if event_vals
            else None,
            "all_first_event_under_3s": all(
                r.get("nfr_first_event_under_3s") for r in ok_runs
            ),
            "model_ttft_ms_min": min(model_vals) if model_vals else None,
            "model_ttft_ms_max": max(model_vals) if model_vals else None,
            "model_ttft_ms_avg": round(sum(model_vals) / len(model_vals), 1)
            if model_vals
            else None,
            "all_model_ttft_under_3s": all(
                r.get("nfr_first_token_under_3s") for r in ok_runs
            ),
        }
    print(json.dumps(summary, indent=2))
    return 0 if ok_runs else 1


if __name__ == "__main__":
    sys.exit(main())
