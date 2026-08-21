from __future__ import annotations

import json
from pathlib import Path

import yaml

from miboe.qualification import build_request_shapes
from miboe.util import artifact_hash, sha256_bytes

ROOT = Path(__file__).parents[1]


def test_committed_w0_request_evidence_matches_serialized_adapter_shapes() -> None:
    evidence_paths = {
        "M01": "evidence/openai/request-shape.closed.json",
        "M02": "evidence/anthropic/request-shape.closed.json",
        "M03": "evidence/google/request-shape.closed.json",
        "M04": "evidence/xai/request-shape.closed.json",
    }
    shapes = build_request_shapes()
    for shape_id, relative in evidence_paths.items():
        evidence = json.loads((ROOT / "waves" / "W0" / relative).read_text(encoding="utf-8"))
        request, audit = shapes[shape_id]
        assert evidence["serialized_body_utf8"].encode() == request.body_bytes
        assert evidence["serialized_body_sha256"] == sha256_bytes(request.body_bytes)
        assert evidence["serialized_body_sha256"] == audit["serialized_request_sha256"]


def test_perplexity_native_and_nonofficial_closed_evidence_matches_adapter() -> None:
    evidence = json.loads(
        (
            ROOT
            / "waves/W0/evidence/perplexity/request-shapes.native-and-w0-closed.json"
        ).read_text(encoding="utf-8")
    )
    shapes = build_request_shapes()
    for evidence_key, shape_id in (
        ("native", "M05"),
        ("closed_diagnostic", "M05_W0_CLOSED_DIAGNOSTIC"),
    ):
        request, audit = shapes[shape_id]
        assert evidence[evidence_key]["serialized_body_utf8"].encode() == request.body_bytes
        assert evidence[evidence_key]["serialized_body_sha256"] == audit[
            "serialized_request_sha256"
        ]
    assert evidence["closed_diagnostic"]["official_w01_observation"] is False


def test_model_lock_candidate_is_fail_closed_with_resolved_m02_w0_candidate() -> None:
    candidate = yaml.safe_load(
        (ROOT / "waves/W0/model-lock.candidate.yaml").read_text(encoding="utf-8")
    )
    models = {row["series_id"]: row for row in candidate["models"]}
    assert candidate["status"] == "INCOMPLETE_NOT_EXECUTABLE"
    assert candidate["official_longitudinal_data"] is False
    assert candidate["execution_permitted"] is False
    assert models["M01"]["requested_model"] == "gpt-5.6-sol"
    assert models["M02"]["permanent_mibo_lineage_id"] == "MIBO-SL-002"
    assert models["M02"]["permanent_lineage_label"] == "Claude"
    assert models["M02"]["requested_model"] == "claude-opus-5"
    assert models["M03"]["requested_model"] == "gemini-3.6-flash"
    assert models["M04"]["requested_model"] == "grok-4.5"
    assert models["M04"]["forbidden_alias"] == "grok-4.5-latest"
    assert models["M05"]["requested_model"] == "sonar"
    assert models["M05"]["environment"] == "NATIVE"
    assert not any(row["live_verified"] for row in models.values())


def test_api_surface_decision_is_not_a_readiness_blocker() -> None:
    capabilities = yaml.safe_load(
        (ROOT / "waves/W0/provider-capabilities.yaml").read_text(encoding="utf-8")
    )
    surface = capabilities["observation_surface"]
    assert surface["official_surface"] == "FIRST_PARTY_API"
    assert surface["consumer_ui_equivalence_assumed"] is False
    assert surface["consumer_ui_equivalence_in_w01_scope"] is False
    assert surface["consumer_ui_non_equivalence_is_readiness_blocker"] is False
    assert capabilities["live_api_execution"]["status"] == (
        "NOT_RUN_CREDENTIALS_ABSENT"
    )


def test_w0_qualification_evidence_manifest_hashes_every_evidence_file() -> None:
    manifest = json.loads(
        (ROOT / "waves/W0/evidence-manifest.json").read_text(encoding="utf-8")
    )
    claimed = manifest.pop("evidence_manifest_sha256")
    assert artifact_hash(manifest) == claimed
    for entry in manifest["entries"]:
        path = ROOT / "waves" / "W0" / entry["path"]
        # Verify canonical Git blob bytes. Windows checkouts may expand LF to
        # CRLF without changing the evidence committed to the repository.
        data = path.read_bytes().replace(b"\r\n", b"\n")
        assert len(data) == entry["bytes"]
        assert sha256_bytes(data) == entry["sha256"]


def test_committed_request_shape_evidence_omits_credential_headers() -> None:
    for path in (ROOT / "waves/W0/evidence").rglob("request-shape*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert '"authorization"' not in text
        assert '"x-api-key"' not in text
        assert '"x-goog-api-key"' not in text
