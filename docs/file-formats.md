# File Formats

Motion, gesture, pose, and BrainOS export files are versioned JSON documents.
Their schemas are packaged under
`src/eric_motion_studio/resources/schemas/` and are enforced at repository
boundaries.

Existing legacy files are read through explicit compatibility handling and are
written in the active schema version. Model references in packaged files are
relative to the package resource root. User-authored motions and exports belong
under the configured mutable data/export directories, never under packaged
resources or `codebase/`.

When changing a format, add a schema version, migration or compatibility test,
and a golden round-trip fixture before changing the writer.
