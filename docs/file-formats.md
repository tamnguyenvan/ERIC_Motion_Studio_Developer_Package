# File Formats

Motion, gesture, pose, and BrainOS export files are versioned JSON documents.
Their schemas are packaged under
`src/eric_motion_studio/resources/schemas/` and are enforced at repository
boundaries.

Existing legacy files are read through explicit compatibility handling and are
written in the active schema version. Model references in packaged files are
relative to the package resource root.

The application uses these writable locations beneath the configured data
directory:

```text
motions/   canonical editable Motion JSON
poses/     single-pose JSON
compiled/  derived dense Gesture JSON
exports/   BrainOS/export artifacts
```

The historical animation schema remains readable and is the current on-disk
representation of `Motion`. “Animation” is retained only as a compatibility
schema name; the UI and domain use “motion.”

Packaged `resources/animations/` and `resources/gestures/` are no longer active
sources. Built-ins are generated from validated definitions and stages. User
files never belong under packaged resources or `codebase/`.

When changing a format, add a schema version, migration or compatibility test,
and a golden round-trip fixture before changing the writer.
