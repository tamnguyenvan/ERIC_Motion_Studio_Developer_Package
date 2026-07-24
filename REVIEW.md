# Review Findings

## P2: Include staged changes in ownership detection

**Location:** `tools/build_artifact_inventory.py:91`

`git ls-files` includes staged files, while `git diff --name-only` reports only
unstaged changes. As a result, a staged new file or modification is classified
as `project (tracked)` and assigned a `keep` decision instead of being preserved
as user working-tree state.

Include the index diff when calculating modified paths, for example with
`git diff --cached --name-only`.

The added test suite passes, but it does not cover this staged-change case.
