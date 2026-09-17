"""Fake local document bytes. Caller input is never a filesystem path."""

import hashlib
import re
from pathlib import Path


class FakeDocumentStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read_fixture(self, external_file_id: str) -> tuple[str, bytes]:
        fixtures = {
            "fixture:source-rights": (
                "Synthetic source rights",
                b"Synthetic research and knowledge only. No outreach permission.",
            ),
            "fixture:operating-notes": (
                "Synthetic operating notes",
                b"Synthetic Company OS research: preserve unknown facts and inspect source provenance.",
            ),
        }
        if external_file_id not in fixtures:
            raise ValueError("Unknown fixture")
        return fixtures[external_file_id]

    def save_snapshot(self, content: bytes) -> str:
        if len(content) > 1_000_000:
            raise ValueError("Snapshot too large")
        key = hashlib.sha256(content).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / key
        if not path.exists():
            try:
                with path.open("xb") as target:
                    target.write(content)
            except FileExistsError:
                pass
        if path.read_bytes() != content:
            raise ValueError("Snapshot integrity failure")
        return key

    def read_snapshot(self, key: str) -> bytes:
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Invalid snapshot key")
        content = (self.root / key).read_bytes()
        if hashlib.sha256(content).hexdigest() != key:
            raise ValueError("Snapshot integrity failure")
        return content
