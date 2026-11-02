"""Export the OpenAPI document deterministically: `python -m app.export_openapi <out.json>`."""

import json
import sys
from pathlib import Path

from app.main import create_app


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.export_openapi <out.json>", file=sys.stderr)
        return 2
    Path(argv[0]).write_text(render(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
