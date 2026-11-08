# README-aware DataMate Plan

**Goal:** Use each shop README as executable semantic context so canonical views and text-to-query decisions respect shop-specific files, joins, units, and special rows.

**Scope:** Extend the existing reader/mapper/canonical/view/decision layers; do not add a new agent framework or dependency.

## Tasks

- [ ] Parse README conventions into compact facts and include them in schema cards.
- [ ] Include README content in cache invalidation.
- [ ] Recognize common README-declared special rows (voucher, points, shipping, service) in canonical lines.
- [ ] Add result-shape/semantic guards before accepting LLM candidates.
- [ ] Add focused tests, run the full suite, then run train evaluation and compare to the saved baseline.

## Success checks

- README parser tests cover column descriptions, conventions, and unit rules.
- Cache key changes when only README changes.
- Existing suite remains green.
- Full train benchmark reports PA, precision, coverage, and answered-only PA.
