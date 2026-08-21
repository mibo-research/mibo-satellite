# Scientific protocol freeze

The authoritative MIBO-Education v1.0 artifacts in this module are imported unchanged from the scientific source bundle and protected by exact file-byte SHA-256 values in `scientific-artifacts.yaml`.

The external `battery/ebb-ja-v1.0.prompt-lock.json` independently locks each of the 70 exact parsed UTF-8 prompt strings. The immutable `waves/W01/scientific-manifest-v1.0.yaml` contains scientific design decisions only. Exact models, schedule, observer site, provider-required controls, governance determinations, and execution timestamps belong only in the separate mutable runtime manifest.

`SCIENTIFIC_PROTOCOL_COMPLETE=true` does not imply `W01_READY=true` or authorize execution.

The scientific protocol materials released as **MIBO-Education Protocol Package v1.0** are reserved at [10.5281/zenodo.22047001](https://doi.org/10.5281/zenodo.22047001) and licensed under [CC BY 4.0](../LICENSE_PROTOCOL.md). The DOI becomes publicly resolvable when the Zenodo Draft is published.
