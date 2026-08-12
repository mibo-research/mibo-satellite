# Scientific protocol freeze

Authoritative MIBO-Education protocol artifacts must be deposited here unchanged, versioned, approved, and hashed. The runtime expects the filenames declared by each Wave Manifest. Placeholder files do not satisfy official preflight.

`scientific-artifacts.yaml` is the machine-readable freeze registry. An artifact is scientifically present only when its status is `FROZEN`, `approved` is true, its expected file exists, and the SHA-256 of the exact file bytes matches the registered hash. A `BLOCKED` entry is not an artifact substitute.

Required source artifacts are listed in `../BLOCKERS.md`.
