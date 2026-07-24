# Phase 7 — Active-Tree Cleanup and Release

Phase 7 completes the refactor delivery boundary. The active tree contains the
packaged application, immutable resources, tests, tools, documentation, and the
supported macOS launcher. The preserved `codebase/` tree is excluded from
cleanup and remains a read-only backup.

The release gate is machine-checkable through `tools/release_audit.py` and CI.
It verifies package/version consistency, the two declared console scripts,
absence of tracked generated artifacts, and absence of active legacy source
duplicates. The documented fresh-clone commands then cover formatting, linting,
tests, headless startup, command audit, cutover audit, viewer startup, and
release audit.
