# Scientific protocol freeze

EIBO preserves the authoritative MIBO-Education v1.0 artifacts unchanged as its legacy scientific record. They remain protected by exact file-byte SHA-256 values in `scientific-artifacts.yaml`; their historical names are not rebranded inside the frozen files.

The external `battery/ebb-ja-v1.0.prompt-lock.json` independently locks each of the 70 exact parsed UTF-8 prompt strings. The immutable `waves/W01/scientific-manifest-v1.0.yaml` contains scientific design decisions only. Exact models, schedule, observer site, provider-required controls, governance determinations, and execution timestamps belong only in the separate mutable runtime manifest.

`SCIENTIFIC_PROTOCOL_COMPLETE=true` does not imply `W01_READY=true` or authorize execution.

The prospective rename and single-human operating/coding model are documented in `amendments/EIBO-PA-001-rename-and-solo-operations.md`. That amendment cannot retroactively satisfy the two-independent-coder requirement in the frozen Codebook v1.0 and remains non-authorizing until an attributed human attestation is recorded.
