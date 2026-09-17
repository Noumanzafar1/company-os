"""Generate deterministic OpenAPI; --check never rewrites the canonical snapshot."""

import argparse
import json
from pathlib import Path

from apps.api.main import create_app


def snapshot() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path("packages/contracts/openapi.json")
    output = snapshot()
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != output:
            raise SystemExit("OpenAPI drift: run npm run contracts and review the diff")
        print("OpenAPI snapshot matches")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
