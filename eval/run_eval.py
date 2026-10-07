"""
Score the question-to-SQL layer (scripts/ask.py) against eval/questions.json.

    python3 eval/run_eval.py

Writes eval/results.md with a per-question breakdown and prints a summary.
Requires ANTHROPIC_API_KEY (see .env.example).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic

from scripts.ask import answer_question

QUESTIONS_PATH = Path("eval/questions.json")
RESULTS_PATH = Path("eval/results.md")


def check_answer(question: dict, scalar) -> bool:
    if scalar is None:
        return False
    if question["tolerance"] == "exact_string":
        return str(scalar).strip().lower() == str(question["expected_answer"]).strip().lower()

    try:
        got = float(scalar)
    except (TypeError, ValueError):
        return False
    expected = float(question["expected_answer"])
    _, rel = question["tolerance"].split(":")
    rel = float(rel)
    return abs(got - expected) <= max(1.0, abs(expected) * rel)


def main():
    questions = json.loads(QUESTIONS_PATH.read_text())
    client = Anthropic()

    rows = []
    n_correct = 0
    for q in questions:
        try:
            result = answer_question(q["question"], client)
            scalar, sql, error = result["scalar"], result["sql"], None
        except Exception as exc:  # noqa: BLE001 - log every failure mode in the eval report
            scalar, sql, error = None, None, str(exc)

        correct = error is None and check_answer(q, scalar)
        n_correct += correct
        rows.append({
            "id": q["id"],
            "question": q["question"],
            "expected": q["expected_answer"],
            "got": scalar,
            "sql": sql,
            "error": error,
            "correct": correct,
        })
        print(f"[{'PASS' if correct else 'FAIL'}] {q['id']:>2} {q['question']}")

    accuracy = n_correct / len(questions)
    print(f"\n{n_correct}/{len(questions)} correct ({accuracy:.0%})")

    lines = [
        "# Question-to-SQL evaluation results\n",
        f"**{n_correct}/{len(questions)} correct ({accuracy:.0%})**\n",
        "| # | Question | Expected | Got | Correct | SQL |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        sql_display = (r["sql"] or r["error"] or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {r['id']} | {r['question']} | {r['expected']} | {r['got']} | "
            f"{'✓' if r['correct'] else '✗'} | `{sql_display}` |"
        )
    RESULTS_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
