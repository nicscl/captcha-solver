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


def diff(baseline: dict, current: dict) -> list[str]:
    regressions = []

    bt, ct = baseline["totals"], current["totals"]
    for k, base_v in bt.items():
        cur_v = ct.get(k, 0)
        if k in WORSE_IF_GREATER and cur_v > base_v:
            regressions.append(f"totals.{k}: {base_v} -> {cur_v}")

    bf, cf = baseline["files"], current["files"]
    for path, base_m in bf.items():
        cur_m = cf.get(path)
        if cur_m is None:
            continue
        for k, base_v in base_m.items():
            cur_v = cur_m.get(k, 0)
            if k in WORSE_IF_GREATER and cur_v > base_v:
                regressions.append(f"{path}:{k}: {base_v} -> {cur_v}")

    return regressions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="grava baseline.json com snapshot atual")
    args = ap.parse_args()

    current = collect()

    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"baseline atualizado: {BASELINE.name}")
        return 0

    if not BASELINE.exists():
        print("ERRO: baseline.json nao existe. Rode com --update para criar.",
              file=sys.stderr)
        return 2

    baseline = json.loads(BASELINE.read_text())
    regressions = diff(baseline, current)

    if regressions:
        print("QUALITY GATE FALHOU — metricas pioraram:", file=sys.stderr)
        for r in regressions:
            print(f"  - {r}", file=sys.stderr)
        print("\nFix the regression OR rode `quality_gate.py --update` "
              "se a piora for intencional e justificada no PR.", file=sys.stderr)
        return 1

    t = current["totals"]
    print(f"OK — {len(current['files'])} arquivos, "
          f"{t['total_loc']} loc, {t['total_funcs']} funcs, "
          f"max_file={t['max_file_loc']}, max_func={t['max_func_loc']}, "
          f"todos={t['total_todos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
