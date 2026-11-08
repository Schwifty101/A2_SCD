#!/usr/bin/env python3
"""Score a running RAHBAR against a golden set, and gate CI on the result (section 5).

    python eval/run_eval.py --api http://<ingress>                 # your corpus
    python eval/run_eval.py --api ... --golden eval/fixtures/golden.fixture.yaml
    python eval/run_eval.py --api ... --update-baseline            # after a deliberate improvement

Exit code 0 when every gate passes, 1 when any fails. CI relies on that exit code.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent

# The gate from section 5.4. Change these only with a reason written in docs/PIPELINE.md.
MAX_RECALL5_DROP = 0.05  # recall@5 may fall at most 5 points below the baseline
MIN_CITATION_VALIDITY = 0.95  # at least 95% of citations must match retrieved passages
REQUIRED_ABSTENTION = 1.0  # every must-abstain question must be declined


def load_golden(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    questions = data.get("questions") or []
    if not questions:
        sys.exit(f"no questions in {path}")
    return questions


def ask(client: httpx.Client, api: str, question: str) -> dict:
    """POST one question and return the AskResponse as a dict (see api/app/schemas.py)."""
    response = client.post(f"{api.rstrip('/')}/api/ask", json={"question": question})
    response.raise_for_status()
    return response.json()


def _matches(rel: dict, ret: dict) -> bool:
    """Match a relevant reference against a retrieved chunk by source and section."""
    rel_src = str(rel.get("source", "")).lower()
    ret_src = str(ret.get("source", "")).lower()
    if rel_src and ret_src and rel_src != ret_src:
        return False

    rel_sec = str(rel.get("section", "")).strip().lower()
    ret_sec = str(ret.get("section", "")).strip().lower()
    if not rel_sec or not ret_sec:
        return True

    # Check for clause number or substring match
    rel_num = re.search(r"(\d+(?:\.\d+)*)", rel_sec)
    ret_num = re.search(r"(\d+(?:\.\d+)*)", ret_sec)
    if rel_num and ret_num and rel_num.group(1) == ret_num.group(1):
        return True

    return rel_sec in ret_sec or ret_sec in rel_sec


def recall_at_k(relevant: list[dict], retrieved: list[dict], k: int) -> float | None:
    """Fraction of the relevant (source, section) pairs found in the top k retrieved.
    Return None when the question has no relevant passages (must-abstain questions).
    """
    if not relevant:
        return None
    top_k = retrieved[:k]
    hits = 0
    for rel in relevant:
        if any(_matches(rel, ret) for ret in top_k):
            hits += 1
    return hits / len(relevant)


def citation_validity(response: dict) -> float | None:
    """Fraction of the response's citations that match a passage in response['retrieved'].
    Return None when there are no citations.
    """
    citations = response.get("citations") or []
    if not citations:
        return None
    retrieved = response.get("retrieved") or []
    valid = 0
    for c in citations:
        if any(_matches(c, r) for r in retrieved):
            valid += 1
    return valid / len(citations)


def summarise(rows: list[dict]) -> dict:
    """Overall recall@3, recall@5, citation validity and abstention correctness, plus
    recall@5 broken down by question type. This dict becomes results.json.
    """
    r3_list, r5_list = [], []
    cv_list = []
    abstain_total = 0
    abstain_correct = 0
    by_type: dict[str, list[float]] = {}

    for r in rows:
        retrieved = r.get("response", {}).get("retrieved") or []
        rel = r.get("relevant") or []
        q_type = r.get("type", "ordinary")

        r3 = recall_at_k(rel, retrieved, 3)
        r5 = recall_at_k(rel, retrieved, 5)

        if r3 is not None:
            r3_list.append(r3)
        if r5 is not None:
            r5_list.append(r5)
            by_type.setdefault(q_type, []).append(r5)

        cv = citation_validity(r.get("response") or {})
        if cv is not None:
            cv_list.append(cv)

        if r.get("must_abstain"):
            abstain_total += 1
            if not r.get("response", {}).get("answered_from_context", True):
                abstain_correct += 1

    recall_at_3 = sum(r3_list) / len(r3_list) if r3_list else 0.0
    recall_at_5 = sum(r5_list) / len(r5_list) if r5_list else 0.0
    cit_val = sum(cv_list) / len(cv_list) if cv_list else 1.0
    abs_corr = (abstain_correct / abstain_total) if abstain_total > 0 else 1.0

    recall_by_type = {t: round(sum(scores) / len(scores), 4) for t, scores in by_type.items()}

    return {
        "recall@3": round(recall_at_3, 4),
        "recall@5": round(recall_at_5, 4),
        "citation_validity": round(cit_val, 4),
        "abstention_correctness": round(abs_corr, 4),
        "recall@5_by_type": recall_by_type,
        "total_questions": len(rows),
        "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def gate(results: dict, baseline: dict | None) -> list[str]:
    """Return one message per failed gate (section 5.4); an empty list means pass."""
    failures: list[str] = []
    r5 = results.get("recall@5", 0.0)
    cit_val = results.get("citation_validity", 1.0)
    abs_corr = results.get("abstention_correctness", 1.0)

    if baseline is not None:
        base_r5 = baseline.get("recall@5", r5)
        if base_r5 - r5 > MAX_RECALL5_DROP:
            failures.append(
                f"recall@5 dropped by {base_r5 - r5:.4f} (allowed max: {MAX_RECALL5_DROP}): {r5:.4f} vs baseline {base_r5:.4f}"
            )

    if cit_val < MIN_CITATION_VALIDITY:
        failures.append(
            f"citation validity {cit_val:.4f} below required {MIN_CITATION_VALIDITY:.4f}"
        )

    if abs_corr < REQUIRED_ABSTENTION:
        failures.append(
            f"abstention correctness {abs_corr:.4f} below required {REQUIRED_ABSTENTION:.4f}"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAHBAR against a golden set.")
    parser.add_argument("--api", required=True, help="base URL, e.g. http://192.168.49.2")
    parser.add_argument("--host", help="Host header, when your Ingress rule names a host")
    parser.add_argument("--golden", type=Path, default=HERE / "golden.yaml")
    parser.add_argument("--baseline", type=Path, default=HERE / "baseline.json")
    parser.add_argument("--out", type=Path, default=HERE / "results.json")
    parser.add_argument(
        "--update-baseline", action="store_true", help="write these results as the new baseline"
    )
    args = parser.parse_args()

    questions = load_golden(args.golden)
    rows = []
    headers = {"Host": args.host} if args.host else {}
    with httpx.Client(timeout=120.0, headers=headers) as client:
        for q in questions:
            started = time.perf_counter()
            response = ask(client, args.api, q["question"])
            rows.append(
                {
                    "id": q["id"],
                    "type": q.get("type", "ordinary"),
                    "must_abstain": bool(q.get("must_abstain", False)),
                    "relevant": q.get("relevant") or [],
                    "expect": q.get("expect"),
                    "response": response,
                    "seconds": round(time.perf_counter() - started, 2),
                }
            )
            print(f"  {q['id']:<5} {rows[-1]['seconds']:>6.2f}s  {q['question'][:60]}")

    results = summarise(rows)
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else None
    failures = gate(results, baseline)

    results["golden"] = str(args.golden)
    results["questions"] = len(rows)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nresults written to {args.out}")
    if args.update_baseline:
        args.baseline.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"baseline updated: {args.baseline}")

    if failures:
        print("\nGATE FAILED")
        for message in failures:
            print(f"  - {message}")
        sys.exit(1)
    print("\ngate passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
