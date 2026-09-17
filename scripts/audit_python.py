"""Opt-in development advisory lookup for public packages in requirements.lock.

Not imported by the application, demo, or offline test suite. No extra dependency.
Only locked public package names/versions are submitted; no source or secrets.
"""

import argparse
import json
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true", required=True)
    parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    packages = re.findall(
        r"^([A-Za-z0-9_.-]+)==([^\s\\]+)",
        (root / "requirements.lock").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not packages:
        raise SystemExit("No pinned packages found")
    request = urllib.request.Request(
        "https://api.osv.dev/v1/querybatch",
        data=json.dumps(
            {
                "queries": [
                    {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
                    for name, version in packages
                ]
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    findings = [
        {"package": name, "version": version, "ids": [v["id"] for v in entry.get("vulns", [])]}
        for (name, version), entry in zip(packages, result["results"], strict=True)
        if entry.get("vulns")
    ]
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "registry": "OSV/PyPI",
        "checked_packages": len(packages),
        "findings": findings,
    }
    output = root / ".local" / "python-security-audit.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    if findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
