# Changelog

## Unreleased

### Changed
- Simplified the Streamlit dashboard to a read-only "proven results" view:
  status metrics, proven theorems with their proofs and peer-review scores,
  and a search over proofs only. Removed the task-prompting UI (study-prompt
  template, queued computations, side questions, SQL console) — proof work is
  now scored by the peer-review pipeline instead of prompted per task.

### Added
- Paper pipeline (`thesius paper export|write|review`): generate a LaTeX paper
  from a theorem's codex records and run an LLM peer review of it. Adapted
  from SakanaAI/AI-Scientist (see THIRD_PARTY_NOTICES.md). New optional
  extras: `paper`, `paper-aider`.
- The pipeline is gated behind the `features.paper` feature flag (off by
  default): `thesius config set features.paper true` or `THESIUS_FEATURE_PAPER=1`.


## v1.0.0

### Added or Changed
- Added this changelog :)
- Fixed typos in both templates
- Back to top links
- Added more "Built With" frameworks/libraries
- Changed table of contents to start collapsed
- Added checkboxes for major features on roadmap

### Removed

- Some packages/libraries from acknowledgements I no longer use