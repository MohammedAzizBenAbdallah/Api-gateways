#!/usr/bin/env python3
"""Evaluate classifier accuracy by calling a running service over HTTP."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

_SVC_ROOT = Path(__file__).resolve().parents[1]
if str(_SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SVC_ROOT))

from app.taxonomy import UNCLASSIFIED, load_taxonomy  # noqa: E402


def _load_eval_rows(eval_file: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with eval_file.open(encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {idx}: {exc}") from exc
            text = str(payload.get("text", "")).strip()
            expected = str(payload.get("expected_intent", "")).strip()
            if not text or not expected:
                raise ValueError(f"Line {idx} must include non-empty 'text' and 'expected_intent'")
            rows.append({"text": text, "expected_intent": expected})
    return rows


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _format_metric(value: float) -> str:
    return f"{value:.4f}"


async def _run(args: argparse.Namespace) -> int:
    if not args.eval_file.is_file():
        print(f"Missing eval file: {args.eval_file}", file=sys.stderr)
        return 2

    taxonomy = load_taxonomy(str(args.taxonomy))
    labels = tuple(taxonomy.candidate_labels) + (UNCLASSIFIED,)

    try:
        rows = _load_eval_rows(args.eval_file)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not rows:
        print("Eval file has no rows", file=sys.stderr)
        return 2

    base = args.service_url.rstrip("/")
    timeout = httpx.Timeout(20.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            health = await client.get(f"{base}/healthz")
            health.raise_for_status()
        except Exception as exc:
            print(f"Service unreachable at {base}: {exc}", file=sys.stderr)
            return 2

        correct = 0
        unclassified_count = 0
        tp = {label: 0 for label in labels}
        fp = {label: 0 for label in labels}
        fn = {label: 0 for label in labels}

        for row in rows:
            resp = await client.post(f"{base}/classify", json={"text": row["text"]})
            resp.raise_for_status()
            data = resp.json()
            pred = str(data.get("intent_label", UNCLASSIFIED))
            if pred not in tp:
                pred = UNCLASSIFIED
            gold = row["expected_intent"]
            if gold not in tp:
                gold = UNCLASSIFIED

            if pred == UNCLASSIFIED:
                unclassified_count += 1
            if pred == gold:
                correct += 1
                tp[gold] += 1
            else:
                fp[pred] += 1
                fn[gold] += 1

    total = len(rows)
    accuracy = correct / total
    print(f"examples={total} correct={correct} accuracy={_format_metric(accuracy)}")
    print(
        f"unclassified_returns={unclassified_count} "
        f"({(100.0 * unclassified_count / total):.2f}%)"
    )
    print("\nPer-intent metrics:")
    for label in labels:
        precision = _safe_div(tp[label], tp[label] + fp[label])
        recall = _safe_div(tp[label], tp[label] + fn[label])
        f1 = _safe_div(2 * precision * recall, precision + recall) if (precision + recall) else 0.0
        print(
            f"- {label}: precision={_format_metric(precision)} "
            f"recall={_format_metric(recall)} f1={_format_metric(f1)}"
        )

    if accuracy < args.accuracy_threshold:
        print(
            f"FAIL: accuracy {accuracy:.4f} < {args.accuracy_threshold:.4f}",
            file=sys.stderr,
        )
        return 1
    print("PASS accuracy gate")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service-url", default="http://localhost:8000")
    ap.add_argument(
        "--eval-file",
        type=Path,
        default=Path("intent_classifier_service/eval/default_test.jsonl"),
    )
    ap.add_argument("--taxonomy", type=Path, default=Path("intent_taxonomy/intent_labels_v1.yaml"))
    ap.add_argument("--accuracy-threshold", type=float, default=0.80)
    args = ap.parse_args()
    if not args.taxonomy.is_file():
        print(f"Missing taxonomy: {args.taxonomy}", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
