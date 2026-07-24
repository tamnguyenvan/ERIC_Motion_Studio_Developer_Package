# Release and Rollback

The initial release is `0.1.0`, declared in both `pyproject.toml` and
`src/eric_motion_studio/__init__.py`. Keep those values synchronized and add a
dated section to `CHANGELOG.md` for each release.

## Release

1. Start from a clean clone and create the documented Python 3.11 virtualenv.
2. Install `.[dev]` and run every command in `docs/testing.md`.
3. Run `tools/release_audit.py` and inspect package contents with
   `python -m build --sdist --wheel` when the build tool is available.
4. Tag the commit with `v<version>` and publish the source or wheel artifact.

## Rollback

Stop the authoring app and viewer, retain user data, and install the previous
version from its tag or artifact. Re-run both self-tests, then restart the app
with the same configured data, export, and runtime-state paths. Do not restore
or delete `codebase/`; it is only a historical reference. If a format migration
has been introduced, restore the last compatible release before opening files
written by the newer release.
