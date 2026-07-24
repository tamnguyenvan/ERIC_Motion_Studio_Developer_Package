# Phase 0 Artifact Review

No cleanup was performed. Existing tracked changes and untracked files are
user-owned and were preserved. `docs/artifact-inventory.tsv` records every
tracked and non-ignored untracked baseline artifact with its SHA-256, owner,
purpose, and disposition.

## Explicit Duplicate and Diagnostic Review

| Artifact | Comparison | Decision |
| --- | --- | --- |
| `eric_motion_studio.py.backup` | SHA-256 `312cce4a…`; differs from authoritative source by 6 insertions and 6 deletions | Archive candidate; preserve pending owner approval |
| `.motion_studio_live_pose 2.json` … `5.json` | Four distinct 17-joint snapshots without sequence IDs | Generated runtime state; ignore and preserve pending owner approval |
| `.motion_studio_live_pose.json` | Current 29-joint state with sequence ID; pre-existing tracked modification | Generated runtime state; ignore future copies and preserve current user change |
| `right_arm_test.py` | Standalone visual MuJoCo experiment using stale Desktop paths | Archive candidate; preserve pending owner approval |
| `talking_test.py` | Standalone visual MuJoCo experiment using stale Desktop paths | Archive candidate; preserve pending owner approval |
| `screenshot.png` | 1280×743 PNG UI capture | Archive candidate; future screenshots ignored |
| `pyside6-file-flags-before-nohidden-20260723-151631.txt` | Qt repair diagnostic inventory | Archive candidate; preserve pending owner approval |
| `qt-plugin-file-flags-before-nohidden-20260723-151527.txt` | Qt plugin repair diagnostic inventory | Archive candidate; preserve pending owner approval |
| `venv-motionstudio-packages-before-repair.txt` | Environment repair package inventory | Archive candidate; preserve pending owner approval |
| tracked `command_audit_reports/` | Existing JSON audit baselines | Keep; new generated reports are ignored |
| caches, logs, local environments | Generated local state | Ignored; no existing user artifact deleted |

The stale `.command` launcher is explicitly non-authoritative. It is retained
only for owner review because it contains obsolete macOS Desktop paths.
