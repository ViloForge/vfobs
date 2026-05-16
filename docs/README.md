# vfobs docs

Repo-local documentation. Design *rationale* and SDD *history*
deliberately live outside this repo (linked below) — these docs
cover **what exists and how to operate/use it**, kept matching
deployed reality.

| Doc | What it answers |
|---|---|
| [`IMPLEMENTATION-STATUS.md`](IMPLEMENTATION-STATUS.md) | **Start here.** What is built, deployed, verified, and still pending — the honest single record across WG1 → WG2 → WG5-min → the OIQ3 fix, plus the load-bearing decisions and lessons. |
| [`scenario-test-runbook.md`](scenario-test-runbook.md) | How to run the kind end-to-end scenario (incl. the vtfstub sidecar, rederived from the real vtaskforge contract). |
| [`../README.md`](../README.md) | Consumer-facing: what vfobs is for and how to emit / query / watch. |

External (not duplicated here — single source of truth):

- **Design:** `viloforge-platform/docs/pipeline-observability-DESIGN.md`,
  `…-IMPLEMENTATION-PLAN.md`, `engineering-principles.md`
- **SDD history** (workgraphs, decisions, gotchas, retros):
  `viloforge-projects/vfobs/workgraphs/{foundation,read-api,
  controller-instrumentation}/`

## Audit note (2026-05-16)

This set was consolidated after a long, course-corrected build.
What changed and why:

- The old `README.md` claimed "WG0 scaffolding" + features that
  don't exist (SSE, DAG views) and a wrong layout — **rewritten**
  to verified reality.
- `IMPLEMENTATION-STATUS.md` **added** as the canonical
  what-exists record (future work is explicitly future-tense).
- `scenario-test-runbook.md`: the vtfstub section described the
  **superseded invented** OIQ3 contract (`/v2/auth/whoami`,
  `/v2/workgraphs/`) — **corrected** to the real
  `/v2/auth/validate/` + DRF `Token` + `/v2/milestones/`, with an
  OIQ3 history note.

Coherence rule for future docs here: state verified reality;
mark unbuilt work future-tense; never carry forward a superseded
external-contract assumption (kb `feedback-external-contract-grounding`).
