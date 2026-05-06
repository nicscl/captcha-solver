import argparse
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from solver import solve


def solve_one(path: Path) -> str:
    ct, _ = mimetypes.guess_type(str(path))
    try:
        return solve(path.read_bytes(), ct or "image/jpeg")
    except Exception as e:
        return f"ERROR {e}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()

    paths = [Path(p) for p in args.paths] or sorted(Path("samples").iterdir())
    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        # executor.map preserva ordem de entrada
        for path, result in zip(paths, ex.map(solve_one, paths)):
            print(f"{path.name}: {result}")
