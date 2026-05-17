#!/usr/bin/env python3
"""Run manual + auto chat API test matrix from the test plan."""
import json
import os
import subprocess
import sys
import time

TESTS = [
    {"id": "1", "phase": "manual", "intent": "general_chat", "prompt": "Say hello in one sentence.", "expect_service": "ollama-llama3"},
    {"id": "2", "phase": "manual", "intent": "code_generation", "prompt": "Write a Python function that reverses a string.", "expect_service": "ollama-DeepSeekCoder"},
    {"id": "3", "phase": "manual", "intent": "summarization", "prompt": "Summarize in one sentence: Kubernetes runs containers across nodes.", "expect_service": "ollama-llama3"},
    {"id": "4", "phase": "manual", "intent": "advanced_chat", "prompt": "Explain the CAP theorem in formal terms.", "expect_service": "gemini-cloud"},
    {"id": "A", "phase": "auto", "intent": "auto", "prompt": "Hey, how are you today?", "expect_intent": "general_chat", "expect_service": "ollama-llama3"},
    {"id": "B", "phase": "auto", "intent": "auto", "prompt": "Fix this bug: my React useEffect runs twice.", "expect_intent": "code_generation", "expect_service": "ollama-DeepSeekCoder"},
    {"id": "C", "phase": "auto", "intent": "auto", "prompt": "TL;DR this paragraph: Kubernetes schedules pods across nodes. Operators manage clusters with declarative configs.", "expect_intent": "summarization", "expect_service": "ollama-llama3"},
    {"id": "D", "phase": "auto", "intent": "auto", "prompt": "Give a rigorous proof sketch for why P != NP is hard to prove.", "expect_intent": "advanced_chat", "expect_service": "gemini-cloud"},
]


def run_measure(intent: str, prompt: str) -> dict:
    env = os.environ.copy()
    env["CHAT_INTENT"] = intent
    env["CHAT_PROMPT"] = prompt
    env["RUNS"] = "1"
    proc = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "measure_first_token.py")],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if proc.returncode != 0 and proc.stdout.strip():
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": proc.stderr or proc.stdout or "no output"}


def fetch_logs_snippet() -> str:
    try:
        proc = subprocess.run(
            [
                "kubectl", "logs", "-n", "ai-application", "deploy/fastapi",
                "--tail=40",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = []
        for line in proc.stdout.splitlines():
            if any(
                k in line
                for k in (
                    "resolved_service",
                    "resolved_intent",
                    "predicted_intent",
                    "Intent classification",
                    "Intent resolution",
                )
            ):
                lines.append(line.strip())
        return lines[-3:] if lines else []
    except Exception as e:
        return [str(e)]


def main() -> int:
    if not os.environ.get("BEARER_TOKEN"):
        print("BEARER_TOKEN required", file=sys.stderr)
        return 1

    results = []
    for t in TESTS:
        print(f"Running test {t['id']} ({t['phase']}) intent={t['intent']}...", flush=True)
        time.sleep(0.5)
        logs_before = len(fetch_logs_snippet())
        out = run_measure(t["intent"], t["prompt"])
        run = (out.get("results") or [{}])[0]
        log_lines = fetch_logs_snippet()
        entry = {
            **t,
            "measure": run,
            "http_status": run.get("http_status"),
            "ok": run.get("ok"),
            "first_event_ms": run.get("first_event_ms"),
            "first_nonempty_token_ms": run.get("first_nonempty_token_ms"),
            "nfr_first_event_under_3s": run.get("nfr_first_event_under_3s"),
            "nfr_model_ttft_under_3s": run.get("nfr_first_token_under_3s"),
            "first_token_preview": run.get("first_token_preview"),
            "stream_error": run.get("stream_error"),
            "error_body": run.get("error_body"),
            "log_snippet": log_lines[-5:],
        }
        results.append(entry)

    report = {"tests": results}
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "chat-test-results.json"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    passed = sum(1 for r in results if r.get("ok"))
    print(f"\nSummary: {passed}/{len(results)} passed", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
