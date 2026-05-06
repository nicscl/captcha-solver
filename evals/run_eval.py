#!/usr/bin/env python3
"""
Tier 3 — Code-based assertions (Parte 2 slides 11-12).

Roda solver no gold set, aplica N assertions por sample, dumpa JSON
machine-readable e (opcional) falha com exit 1 se threshold nao bater.

Diferenca pro error_analysis.py:
  - error_analysis: leitura humana + CSV pra cluster manual
  - run_eval: assertions formalizadas + JSON + gating automatico

Assertions:
  - non_empty:        len(got) > 0
  - no_error:         got nao comeca com 'ERROR:'
  - length_match:     len(got) == len(expected)
  - charset_alnum:    todos os chars de got sao [A-Za-z0-9]
  - exact_match:      got == expected
  - ci_match:         got.lower() == expected.lower()
  - close_match:      edit_distance(got, expected) <= 1

Uso:
  python3 evals/run_eval.py
  python3 evals/run_eval.py --limit 10
  python3 evals/run_eval.py --threshold exact_match=0.85 --threshold close_match=1.0
  python3 evals/run_eval.py --out evals/results/baseline.json
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT))

from solver import MODEL, solve  # noqa: E402

GOLD = ROOT / "gold.json"
RESULTS_DIR = ROOT / "results"
ALNUM = set(string.ascii_letters + string.digits)

USE_COLOR = sys.stdout.isatty()


def c(s, code):
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def edit_distance(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def assertions_for(got: str, expected: str) -> dict[str, bool]:
    is_err = got.startswith("ERROR:")
    return {
        "non_empty": len(got) > 0,
        "no_error": not is_err,
        "length_match": (not is_err) and len(got) == len(expected),
        "charset_alnum": (not is_err) and all(ch in ALNUM for ch in got),
        "exact_match": got == expected,
        "ci_match": got.strip().lower() == expected.strip().lower(),
        "close_match": (not is_err) and edit_distance(got, expected) <= 1,
    }


def run_one(item: dict) -> dict:
    p = ROOT / item["path"]
    ct, _ = mimetypes.guess_type(str(p))
    expected = item["expected"]
    try:
        got = solve(p.read_bytes(), ct or "image/png")
    except Exception as e:
        got = f"ERROR:{type(e).__name__}:{e}"
    return {
        "path": item["path"],
        "source": item.get("source", ""),
        "kind": item.get("kind", ""),
        "expected": expected,
        "got": got,
        "edit_dist": edit_distance(got, expected) if not got.startswith("ERROR:") else None,
        "assertions": assertions_for(got, expected),
    }


def aggregate(samples: list[dict]) -> dict[str, dict]:
    keys = list(samples[0]["assertions"].keys())
    summary = {}
    for k in keys:
        passed = sum(1 for s in samples if s["assertions"][k])
        summary[k] = {
            "passed": passed,
            "total": len(samples),
            "pass_rate": round(passed / len(samples), 4),
        }
    return summary


def group_by(samples: list[dict], field: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = {}
    for s in samples:
        key = s.get(field, "")
        if not key:
            continue
        if field == "source":
            key = key.split(":")[0]
        groups.setdefault(key, []).append(s)
    return {k: aggregate(v) for k, v in groups.items()}


def parse_thresholds(items: list[str]) -> dict[str, float]:
    out = {}
    for raw in items:
        if "=" not in raw:
            raise SystemExit(f"--threshold espera key=value, recebeu: {raw!r}")
        k, v = raw.split("=", 1)
        out[k.strip()] = float(v)
    return out


def check_thresholds(summary: dict[str, dict],
                     thresholds: dict[str, float]) -> list[str]:
    failures = []
    for key, min_rate in thresholds.items():
        if key not in summary:
            failures.append(f"{key}: assertion desconhecida")
            continue
        actual = summary[key]["pass_rate"]
        if actual < min_rate:
            failures.append(f"{key}: {actual:.2%} < {min_rate:.2%} (min)")
    return failures


def print_row(i: int, n: int, s: dict) -> None:
    a = s["assertions"]
    if a["exact_match"]:
        sym = c("✓", "32;1")
    elif a["close_match"]:
        sym = c("~", "33;1")
    else:
        sym = c("✗", "31;1")
    name = s["path"].split("/")[-1]
    got_repr = f"{s['got']!r}"
    if not a["exact_match"]:
        got_repr = c(got_repr, "33" if a["close_match"] else "31")
    d = s["edit_dist"] if s["edit_dist"] is not None else "?"
    print(f"  {sym} [{i:2d}/{n}] {name:<22} "
          f"expected={s['expected']!r:<14} got={got_repr} "
          f"{c('(d=' + str(d) + ')', '2')}")


def print_assertions_table(summary: dict[str, dict]) -> None:
    print()
    print(c("assertions:", "1"))
    width = 18
    for k, v in summary.items():
        rate = v["pass_rate"]
        bar_n = int(20 * rate)
        bar = "█" * bar_n + "░" * (20 - bar_n)
        color = "32" if rate == 1.0 else ("33" if rate >= 0.85 else "31")
        print(f"  {k:<{width}} {c(bar, color)} "
              f"{v['passed']:>2}/{v['total']} ({rate:.0%})")


def print_groups(label: str, groups: dict[str, dict], key: str) -> None:
    if not groups:
        return
    print()
    print(c(f"{label}:", "1"))
    for name, summary in sorted(groups.items()):
        cell = summary[key]
        rate = cell["pass_rate"]
        bar_n = int(20 * rate)
        bar = "█" * bar_n + "░" * (20 - bar_n)
        color = "32" if rate == 1.0 else ("33" if rate >= 0.85 else "31")
        print(f"  {name:<12} {c(bar, color)} "
              f"{cell['passed']:>2}/{cell['total']} ({rate:.0%})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--threshold", action="append", default=[],
                    metavar="KEY=VAL",
                    help="ex: --threshold exact_match=0.85; pode repetir")
    ap.add_argument("--out", type=Path, default=None,
                    help="caminho do JSON; default evals/results/run_<ts>.json")
    ap.add_argument("--concurrency", type=int, default=5,
                    help="N de chamadas OpenRouter em paralelo (default 5)")
    args = ap.parse_args()

    if "OPENROUTER_API_KEY" not in os.environ:
        print(c("ERRO", "31"),
              "OPENROUTER_API_KEY nao setada. Rode via ./run.sh eval3 ou "
              "carregue ../.env primeiro.", file=sys.stderr)
        return 2

    items = json.loads(GOLD.read_text())
    if args.limit:
        items = items[: args.limit]

    n = len(items)
    print(c(f"run_eval — {n} amostras (model={MODEL})", "1;36"))
    print()

    # paraleliza N chamadas de OpenRouter; mantém ordem de input nas saídas
    samples: list[dict] = [None] * n  # type: ignore[list-item]
    done = 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        fut_to_idx = {ex.submit(run_one, item): i
                      for i, item in enumerate(items)}
        for fut in as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            samples[idx] = fut.result()
            done += 1
            print_row(done, n, samples[idx])

    summary = aggregate(samples)
    by_kind = group_by(samples, "kind")
    by_source = group_by(samples, "source")
    thresholds = parse_thresholds(args.threshold)

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result = {
        "timestamp": ts,
        "model": MODEL,
        "n_samples": n,
        "summary": summary,
        "by_kind": by_kind,
        "by_source": by_source,
        "thresholds": thresholds,
        "samples": samples,
    }

    out_path = (args.out or RESULTS_DIR
                / f"run_{time.strftime('%Y%m%d-%H%M%S')}.json").resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n")

    print_assertions_table(summary)
    print_groups("por kind (synthetic)", by_kind, "exact_match")
    print_groups("por source", by_source, "exact_match")

    failures = check_thresholds(summary, thresholds) if thresholds else []
    print()
    print(c("─" * 70, "2"))
    try:
        rel = out_path.relative_to(PROJECT)
    except ValueError:
        rel = out_path
    print(f"{c('JSON:', '36')} {rel}")

    if failures:
        print(c("✗ THRESHOLDS FALHARAM:", "1;31"))
        for f in failures:
            print(f"    {c('•', '31')} {f}")
        return 1

    if thresholds:
        print(c(f"✓ todos os {len(thresholds)} threshold(s) passaram",
                "1;32"))
    else:
        print(c("(sem --threshold; rodada informacional)", "2"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
