from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .util import canonical_json, canonical_json_bytes, sha256_bytes, write_immutable


def export_blind(wave_dir: Path, *, salt: str) -> dict[str, Any]:
    if len(salt) < 16:
        raise ValidationError("blind salt must be at least 16 characters")
    source = wave_dir / "L1_canonical" / "observations.jsonl"
    if not source.exists():
        raise ValidationError("L1 canonical data is missing; run QC first")
    records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]
    identities = sorted(
        {
            (row["provider"], row["series_id"], row["requested_model"])
            for row in records
            if row["scientifically_completed"]
        }
    )
    mapping = {
        identity: "MODEL-"
        + hashlib.sha256((salt + "\0" + "\0".join(identity)).encode("utf-8"))
        .hexdigest()[:12]
        .upper()
        for identity in identities
    }
    blinded: list[str] = []
    for original in records:
        if not original["scientifically_completed"]:
            continue
        row = dict(original)
        identity = (row.pop("provider"), row.pop("series_id"), row.pop("requested_model"))
        row.pop("returned_model", None)
        row.pop("observation_id", None)
        row["blind_model_id"] = mapping[identity]
        blinded.append(canonical_json(row))
    data = (("\n".join(blinded) + "\n") if blinded else "").encode("utf-8")
    export_path = wave_dir / "exports" / "blind-observations.jsonl"
    key_path = wave_dir / "exports" / "RESTRICTED-blind-key.json"
    write_immutable(export_path, data)
    key = {
        "schema_version": "1.0",
        "notice": "RESTRICTED UNBLINDING KEY; salt is not stored",
        "mapping": [
            {
                "blind_model_id": blind,
                "provider": key[0],
                "series_id": key[1],
                "requested_model": key[2],
            }
            for key, blind in sorted(mapping.items())
        ],
        "blind_export_sha256": sha256_bytes(data),
    }
    write_immutable(key_path, canonical_json_bytes(key) + b"\n")
    return {
        "records": len(blinded),
        "export": str(export_path),
        "key": str(key_path),
        "sha256": sha256_bytes(data),
    }
