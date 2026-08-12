from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_repository_manifest_hashes_every_declared_file() -> None:
    repository = Path(__file__).resolve().parents[3]
    manifest_path = repository / "FILE_MANIFEST.json"
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert entries == sorted(entries, key=lambda entry: entry["path"])
    assert len({entry["path"] for entry in entries}) == len(entries)

    for entry in entries:
        path = repository / entry["path"]
        data = path.read_bytes()
        assert len(data) == entry["bytes"], entry["path"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["path"]
