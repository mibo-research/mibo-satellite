# MIBO-Education v1.1: current protocol entry point

The prospective W01 amendment is published on Zenodo:
[10.5281/zenodo.24157241](https://doi.org/10.5281/zenodo.24157241).
It is English-language protocol material under CC BY 4.0, not W01 results.
Author: Kento Sasano, ORCID [0009-0009-3853-8029](https://orcid.org/0009-0009-3853-8029).
Affiliations and funding, competing-interest and AI-assistance disclosures remain unchanged.

## Authoritative content and preservation

The exact reviewed implementation, instruments, scoring specifications and tests are
distributed in the unchanged [adopted content ZIP](releases/v1.1/MIBO-Education-W01-v1.1-registration-preparation-DRAFT-20261112.zip).
Its SHA-256 is:

```text
4854f94fb63fe7d63a7d318a45372c9daeae718c696b724239c76f2c17398da3
```

The approved preparation release SHA-256 is:

```text
64c257ffaf13e447dca643275fa46e8dcdf7beef9ab100a4ed1fb7fc26438f36
```

The [dated finalization declaration](protocol/registration/finalization-declaration-v1.1-20261112.json)
adopts those exact bytes as formal v1.1. DRAFT/preparation labels inside the ZIP
and pre-publication companion metadata are retained historical facts, not current
execution authority. The later [publication receipt](protocol/registration/education-v1.1-published-receipt-20261112.json)
records actual DOI resolution and exact-byte verification of all four Zenodo files.
Use [CITATION-v1.1.cff](CITATION-v1.1.cff) for this amendment; retain the old citation for historical v1.0.

The original [v1.0 record](https://doi.org/10.5281/zenodo.22047001), old ZIP,
frozen scientific files, W0 data, judgments, accounting and machine flags are preserved.
W0 remains nonofficial engineering evidence; it is not promoted to the official baseline.
Runtime source code retains the existing repository license; the scoped scientific
protocol materials remain CC BY 4.0.

This publication PR distributes the approved implementation as its byte-locked ZIP.
The expanded historical v1.0 harness and its manual GitHub execution workflows are
not the v1.1 production route and must not be used to start W01. The approved route
inside the ZIP is `runtime/start-w01-v1.1.ps1` with its separately initialized,
private, publication-bound FINAL authorization. No credential or raw observation
data is included in the public release.

## Approved W01 scope

| Stage | Approved window | Maximum new requests |
|---|---|---:|
| Metadata + common calibration | 19 Nov 2026 09:00 JST to 20 Nov 09:00 JST | 6 + 105 |
| W01 collection | 20 Nov 2026 09:00 JST; target 12 h, hard 24 h | 2,100 |
| Nonself judging | Within 72 h after actual collection completion | 4,200 |

New ceiling: **6,411**; preserve **1,468** prior reservations; cumulative ceiling:
**7,879**. Each slot has one attempt, with zero automatic resends. These are
reservation ceilings, not guaranteed successful samples or a USD spending guarantee.

| Source | Requested source model | The two nonself judges |
|---|---|---|
| M01 OpenAI | `gpt-5.6-sol` | Anthropic `claude-opus-5-5`, Gemini `gemini-3.8-flash` |
| M02 Anthropic | `claude-opus-5` | Gemini `gemini-3.8-flash`, OpenAI `gpt-6.1-sol` |
| M03 Gemini | `gemini-3.6-flash` | Anthropic `claude-opus-5-5`, OpenAI `gpt-6.1-sol` |

Observe 70 frozen Japanese items with 10 replications per source. Repeat the approved
35-example common calibration for all three judges, applying both fixed numerical
guards and an explicit delegated limited definition/adversarial technical review
before collection. No silent model, prompt, anchor, schedule or criterion substitution.

Fully recorded READ_TIMEOUTs consume reservations and remain missing; only unsent
slots may continue. Missing source cells are not refilled, and their two judging
requests are not sent. Unknown outcomes, HTTP/authentication, identity or CLOSED
control failures stop execution. Scientific refusals, blocking, truncation, poor
answers and invalid model outputs are preserved, not repaired or retried.

AC-connected execution alone may inhibit automatic sleep, with clear/close on normal
exit, error or AC loss. No permanent power change. **No Core, W0 restart or other wave**
is authorized by this release. Scheduled execution is conditional on publication-bound
FINAL authority, phase clocks and fresh qualification; publication is not proof that
W01 has run or that the six models remain available at execution time.

## Manuscript and interpretation

The [three-page English addendum](releases/v1.1/MIBO-Education-v1.1-methods-addendum-20261112.pdf)
prospectively supersedes conflicting historical v1.0 methods for W01 only.
The [SSRN version PDF](releases/v1.1/MIBO-Education-paper-v1.1-SSRN-20261112.pdf)
prepends it to the retained 14-page manuscript; original page content streams are unchanged.
The existing paper identifier remains [10.2139/ssrn.7330038](https://doi.org/10.2139/ssrn.7330038).
Submission/moderation status is separate from the existing public SSRN version.

W01 is a baseline, not demonstrated longitudinal drift. Report within-source domain
means, valid denominators, unresolved/missing counts and descriptive distributions.
No overall AI ranking, pooled changing-rater kappa, independence-based confidence
interval, human-gold validity, all-45-field semantic validation or cross-source
comparability is asserted. AI scorers and delegated technical review are disclosed;
AI systems are not independent human raters or authors.
