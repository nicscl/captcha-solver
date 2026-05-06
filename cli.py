import mimetypes
import sys
from pathlib import Path

from solver import solve

if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(Path("samples").iterdir())
    for path in paths:
        p = Path(path)
        ct, _ = mimetypes.guess_type(str(p))
        try:
            result = solve(p.read_bytes(), ct or "image/jpeg")
            print(f"{p.name}: {result}")
        except Exception as e:
            print(f"{p.name}: ERROR {e}")
