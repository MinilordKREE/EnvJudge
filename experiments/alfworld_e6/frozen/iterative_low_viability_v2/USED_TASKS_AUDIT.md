# V2 used-task audit: fresh train bridge seeds

**Smallest unused ID: 150. First 20 unused IDs: 150–169, ascending.**
The independently derived actual train bridge-seed set is 0–149.

## Read-only verification

Rehashed **55,970 files / 12,675,309,919 bytes** across both
worktrees and archived ALFWorld pilots. Every one of the **55,841** sources in the
previous audit remains byte-identical; 129 files were added and none were removed.
Extraction was reused only after its full file hash matched. New and changed
records were scanned for actual bridge seeds and historical task labels.
No actual train task ID outside the derived consumed set was found.

The previous audit binds IDs 0–129. The previous fresh-pool run supplies exactly
**26 original identity traces with 26 unique episode IDs covering 130–149**.
Their file hashes, canonical trace hashes, bridge seeds and episode IDs all match
the frozen screening records. That run remains **INSUFFICIENT_FRESH_LOW**; this
audit neither resumes nor reclassifies any prior task.

## Preserved history and domains

- All **61** published artifact-manifest bindings match.
- All **98** previous final screening-audit source bindings match.
- **21** old tracked report, frozen-input and driver files match starting HEAD.
- All **110** old run files receive V2-starting hashes. Older unpublished
  stderr/lock hashes are not claimed retroactively.
- The real integration seeds are already consumed. Fake unit identifiers do not
  count as execution.
- Generic request, extraction and sampling RNG seeds, and held-out evaluation
  split seeds remain separate from train bridge seeds. There are **zero newly
  unclassified seed/path pairs**.

The compact JSON binds both reproducible scripts, the full local metadata
inventory, prior audit, all 26 newly consumed traces, and the previous run's
starting hashes. No raw trajectory text, prompt, API key or future task semantics
is exported. No API call, environment reset or worktree write was performed.

## Limits

The audit covers all extant records in its declared workspace scope. It cannot
prove absence of unrecorded activity outside that scope. Re-running the scanner
after new experiments will naturally change the consumed set; this audit is the
immutable snapshot taken before V2 paid screening.
