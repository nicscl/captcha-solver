#!/usr/bin/env python3
"""
Quality Gate — efeito catraca (ratchet).

Compara métricas atuais do código vs `baseline.json`. A regra é simples:
métrica nunca piora. Empata ou melhora. Qualquer regressão -> exit 1.

Métricas por arquivo .py (excluindo samples/, .venv/, __pycache__/):
  - loc:           linhas executáveis (sem branco/comentário)
  - funcs:         número de defs
  - max_func_loc:  maior função em LOC
  - todos:         contagem de TODO/FIXME/XXX

Métricas globais:
  - total_loc, total_funcs, total_todos, max_file_loc, max_func_loc

Uso:
  python3 quality_gate.py            # checa; exit 1 se regrediu
  python3 quality_gate.py --update   # regrava baseline.json com snapshot atual
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASELINE = ROOT / "baseline.json"
EXCLUDE_DIRS = {"samples", ".venv", "__pycache__", ".git"}


def iter_py_files() -> list[Path]:
    files = []
    for p in ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.relative_to(ROOT).parts):
            continue
        files.append(p)
    return sorted(files)


def file_metrics(path: Path) -> dict:
    src = path.read_text()
    loc = 0
    todos = 0
    for line in src.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if "TODO" in s or "FIXME" in s or "XXX" in s:
                todos += 1
            continue
        loc += 1

    funcs = 0
    max_func_loc = 0
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs += 1
                end = getattr(node, "end_lineno", node.lineno)
                fl = end - node.lineno + 1
                if fl > max_func_loc:
                    max_func_loc = fl
    except SyntaxError:
        pass

    return {"loc": loc, "funcs": funcs, "max_func_loc": max_func_loc, "todos": todos}


def collect() -> dict:
    per_file = {}
    for p in iter_py_files():
        rel = str(p.relative_to(ROOT))
        per_file[rel] = file_metrics(p)
    totals = {
        "total_loc": sum(m["loc"] for m in per_file.values()),
        "total_funcs": sum(m["funcs"] for m in per_file.values()),
        "total_todos": sum(m["todos"] for m in per_file.values()),
        "max_file_loc": max((m["loc"] for m in per_file.values()), default=0),
        "max_func_loc": max((m["max_func_loc"] for m in per_file.values()), default=0),
    }
    return {"files": per_file, "totals": totals}


WORSE_IF_GREATER = {"loc", "max_func_loc", "todos",
                    "total_loc", "total_todos", "max_file_loc"}


USE_COLOR = sys.stdout.isatty()
C_RESET = "\033[0m" if USE_COLOR else ""
C_DIM = "\033[2m" if USE_COLOR else ""
C_BOLD = "\033[1m" if USE_COLOR else ""
C_GREEN = "\033[32m" if USE_COLOR else ""
C_RED = "\033[31m" if USE_COLOR else ""
C_YELLOW = "\033[33m" if USE_COLOR else ""
C_CYAN = "\033[36m" if USE_COLOR else ""

METRIC_LABELS = {
    "loc": "loc",
    "funcs": "funcs",
    "max_func_loc": "max_func_loc",
    "todos": "todos",
    "total_loc": "total_loc",
    "total_funcs": "total_funcs",
    "total_todos": "total_todos",
    "max_file_loc": "max_file_loc",
}


def classify(metric: str, base: int, cur: int) -> tuple[str, str, str]:
    """Return (symbol, color, note) for a metric comparison."""
    delta = cur - base
    if delta == 0:
        return "=", C_DIM, "unchanged"
    if metric in WORSE_IF_GREATER:
        if delta > 0:
            return "✗", C_RED, f"REGRESSION (+{delta})"
        return "↓", C_GREEN, f"improved ({delta})"
    if delta > 0:
        return "+", C_YELLOW, f"+{delta} (no rule)"
    return "-", C_DIM, f"{delta}"


def render_row(metric: str, base: int, cur: int) -> str:
    sym, color, note = classify(metric, base, cur)
    label = METRIC_LABELS.get(metric, metric)
    return (f"    {color}{sym}{C_RESET} {label:<14} "
            f"{base:>4} → {cur:<4}  {color}{note}{C_RESET}")


def render_report(baseline: dict, current: dict) -> tuple[str, list[str]]:
    """Build full report; return (text, regressions)."""
    lines = []
    regressions = []

    bf, cf = baseline["files"], current["files"]
    all_files = sorted(set(bf) | set(cf))

    lines.append(f"{C_BOLD}{C_CYAN}Quality Gate — captcha-solver{C_RESET}")
    lines.append(f"{C_DIM}baseline: {BASELINE.name}  |  "
                 f"{len(current['files'])} arquivos analisados{C_RESET}")
    lines.append("")
    lines.append(f"{C_BOLD}por arquivo{C_RESET}")

    for path in all_files:
        base_m = bf.get(path)
        cur_m = cf.get(path)
        if base_m is None:
            lines.append(f"\n  {C_YELLOW}[NEW]{C_RESET} {path}")
            for k, v in cur_m.items():
                lines.append(f"    + {METRIC_LABELS.get(k, k):<14} "
                             f"{'-':>4} → {v:<4}  {C_YELLOW}new file{C_RESET}")
            continue
        if cur_m is None:
            lines.append(f"\n  {C_DIM}[REMOVED] {path}{C_RESET}")
            continue

        lines.append(f"\n  {C_BOLD}{path}{C_RESET}")
        for k, base_v in base_m.items():
            cur_v = cur_m.get(k, 0)
            lines.append(render_row(k, base_v, cur_v))
            if k in WORSE_IF_GREATER and cur_v > base_v:
                regressions.append(f"{path}:{k}: {base_v} → {cur_v}")

    lines.append("")
    lines.append(f"{C_BOLD}totais{C_RESET}")
    bt, ct = baseline["totals"], current["totals"]
    for k, base_v in bt.items():
        cur_v = ct.get(k, 0)
        lines.append(render_row(k, base_v, cur_v))
        if k in WORSE_IF_GREATER and cur_v > base_v:
            regressions.append(f"totals.{k}: {base_v} → {cur_v}")

    lines.append("")
    lines.append("─" * 60)
    if regressions:
        lines.append(f"{C_BOLD}{C_RED}✗ FALHOU{C_RESET} — "
                     f"{len(regressions)} metrica(s) pioraram:")
        for r in regressions:
            lines.append(f"    {C_RED}•{C_RESET} {r}")
        lines.append("")
        lines.append(f"{C_DIM}Corrija a regressao OU rode "
                     f"`quality_gate.py --update` se a piora for "
                     f"intencional (justifique no PR).{C_RESET}")
    else:
        improved = sum(1 for path in cf for k, v in cf[path].items()
                       if path in bf and k in WORSE_IF_GREATER
                       and v < bf[path].get(k, v))
        lines.append(f"{C_BOLD}{C_GREEN}✓ PASSOU{C_RESET} — "
                     f"todas as metricas dentro do baseline"
                     + (f" ({improved} melhoria(s))" if improved else ""))

    return "\n".join(lines), regressions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="grava baseline.json com snapshot atual")
    args = ap.parse_args()

    current = collect()

    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"{C_GREEN}✓{C_RESET} baseline atualizado: {BASELINE.name}")
        return 0

    if not BASELINE.exists():
        print(f"{C_RED}ERRO{C_RESET}: baseline.json nao existe. "
              f"Rode com --update para criar.", file=sys.stderr)
        return 2

    baseline = json.loads(BASELINE.read_text())
    report, regressions = render_report(baseline, current)
    out = sys.stderr if regressions else sys.stdout
    print(report, file=out)
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
