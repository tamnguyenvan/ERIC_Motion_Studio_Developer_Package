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
compiled/  legacy or internal derived Gesture JSON
exports/   BrainOS/export artifacts
```

The Motion Library manages editable Motion files. Playback and export derive
dense trajectories automatically; no approval or manual compiled-artifact step
is required. The `compiled/` directory remains reserved for migrated legacy
files and internal compatibility.

Pose V1 files may include `pose_id`, `pose_name`, `pose_description`,
`pose_aliases`, `pose_tags`, `pose_body_regions`, and `library_origin`.
These optional fields power local Pose Library search while preserving
compatibility with older pose files that only contain joint offsets.

The historical animation schema remains readable and is the current on-disk
representation of `Motion`. “Animation” is retained only as a compatibility
schema name; the UI and domain use “motion.”

Packaged `resources/animations/` and `resources/gestures/` are no longer active
sources. Built-ins are generated from validated definitions and stages. User
files never belong under packaged resources or `codebase/`.

When changing a format, add a schema version, migration or compatibility test,
and a golden round-trip fixture before changing the writer.
