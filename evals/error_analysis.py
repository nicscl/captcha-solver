#!/usr/bin/env python3
"""
Hamel's #1 rule: error analysis FIRST.

Roda o solver em todo gold set, mostra lado-a-lado expected vs got,
e dumpa CSV pra voce labelar os modos de falha na mao antes de
buildar qualquer pipeline de eval automatico.

Saida:
  - terminal: tabela colorida + summary (exact, case-insensitive,
    edit-distance), breakdown por fonte e por kind (synthetic)
  - evals/runs/run_<timestamp>.csv: planilha com colunas vazias
    'label' e 'note' pra cluster manual

Uso:
  python3 evals/error_analysis.py             # roda tudo
  python3 evals/error_analysis.py --limit 10  # so primeiras N
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT))

from solver import solve  # noqa: E402

GOLD = ROOT / "gold.json"
RUNS = ROOT / "runs"

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


def normalize(s: str) -> str:
    return s.strip().lower()


def status_symbol(exact: bool, ci: bool) -> str:
    if exact:
        return c("✓", "32;1")
    if ci:
        return c("~", "33;1")
    return c("✗", "31;1")


def run_one(item: dict) -> dict:
    p = ROOT / item["path"]
    ct, _ = mimetypes.guess_type(str(p))
    expected = item["expected"]
    try:
        got = solve(p.read_bytes(), ct or "image/png")
    except Exception as e:
        got = f"ERROR:{e}"
    exact = got == expected
    ci = normalize(got) == normalize(expected)
    return {
        "path": item["path"],
        "source": item.get("source", ""),
        "kind": item.get("kind", ""),
        "expected": expected,
        "got": got,
        "exact": exact,
        "ci_match": ci,
        "edit_dist": edit_distance(got, expected),
        "label": "",
        "note": "",
    }


def print_row(i: int, n: int, r: dict) -> None:
    sym = status_symbol(r["exact"], r["ci_match"])
    expected_col = c(f"{r['expected']!r:<14}", "1")
    got_col = f"{r['got']!r}"
    if not r["exact"]:
        got_col = c(got_col, "31" if not r["ci_match"] else "33")
    name = r["path"].split("/")[-1]
    print(f"  {sym} [{i:2d}/{n}] {name:<22} "
          f"expected={expected_col} got={got_col} "
          f"{c('(d=' + str(r['edit_dist']) + ')', '2')}")


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(exist_ok=True)
    fields = ["path", "source", "kind", "expected", "got",
              "exact", "ci_match", "edit_dist", "label", "note"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def print_summary(rows: list[dict]) -> None:
    n = len(rows)
    exact = sum(r["exact"] for r in rows)
    ci = sum(r["ci_match"] for r in rows)
    close = sum(r["edit_dist"] <= 1 for r in rows)
    avg_d = sum(r["edit_dist"] for r in rows) / n if n else 0

    print()
    print(c("─" * 70, "2"))
    print(f"{c('SUMMARY', '1;36')}  total={n}  "
          f"exact={exact}/{n} ({exact/n:.0%})  "
          f"ci={ci}/{n} ({ci/n:.0%})  "
          f"close(d≤1)={close}/{n} ({close/n:.0%})  "
          f"avg_edit={avg_d:.2f}")

    by_src: dict[str, list[int]] = {}
    for r in rows:
        s = r["source"].split(":")[0] or "unknown"
        by_src.setdefault(s, [0, 0])
        by_src[s][0] += 1
        by_src[s][1] += int(r["exact"])
    print()
    print(c("por fonte:", "1"))
    for src, (total, hits) in sorted(by_src.items()):
        bar = "█" * int(20 * hits / total) + "░" * (20 - int(20 * hits / total))
        print(f"  {src:<12} {bar} {hits}/{total} ({hits/total:.0%})")

    by_kind: dict[str, list[int]] = {}
    for r in rows:
        k = r["kind"]
        if k:
            by_kind.setdefault(k, [0, 0])
            by_kind[k][0] += 1
            by_kind[k][1] += int(r["exact"])
    if by_kind:
        print()
        print(c("por kind (synthetic):", "1"))
        for k, (total, hits) in sorted(by_kind.items()):
            bar = ("█" * int(20 * hits / total)
                   + "░" * (20 - int(20 * hits / total)))
            print(f"  {k:<12} {bar} {hits}/{total} ({hits/total:.0%})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="roda so as N primeiras")
    args = ap.parse_args()

    if "OPENROUTER_API_KEY" not in os.environ:
        print(c("ERRO", "31"), "OPENROUTER_API_KEY nao setada. "
              "Rode via ./run.sh ou source ../.env primeiro.",
              file=sys.stderr)
        return 2

    items = json.loads(GOLD.read_text())
    if args.limit:
        items = items[: args.limit]

    n = len(items)
    print(c(f"Error analysis — {n} amostras (Hamel #1 rule)", "1;36"))
    print(c(f"gold: {GOLD.name} | "
            f"reais={sum(1 for x in items if 'real' in x.get('source', ''))} "
            f"synth={sum(1 for x in items if x.get('source') == 'synthetic')}",
            "2"))
    print()

    rows = []
    for i, item in enumerate(items, 1):
        row = run_one(item)
        rows.append(row)
        print_row(i, n, row)

    ts = time.strftime("%Y%m%d-%H%M%S")
    csv_path = RUNS / f"run_{ts}.csv"
    write_csv(rows, csv_path)

    print_summary(rows)

    print()
    print(c("─" * 70, "2"))
    print(f"{c('CSV pra labeling:', '36')} "
          f"{csv_path.relative_to(PROJECT)}")
    print(c("Hamel: agora le os errados em voz alta. Adiciona razao "
            "em 'note', cluster em 'label'. Volta com 3-5 failure modes.",
            "2"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
