# Pose Library

The Pose Library provides reusable static joint configurations without file
dialogs in the normal workflow.

## User workflow

1. Open the **Poses** tab.
2. Search by name, intent, alias, tag, or body region.
3. Click a result to stop active playback and apply it to the joint editor and
   MuJoCo preview.
4. Adjust joints if needed.
5. Use **Capture** or **Add Keyframe** to commit the preview into the current
   motion.

Built-ins are read-only. **Duplicate** creates a custom copy. **Save Current**
stores the current joint preview as a custom pose. Custom poses support Update,
Duplicate, Rename, and Delete.

The File menu retains **Import Pose** and **Export Current Pose** for
portability. Those file dialogs are not required for normal library use.

## Search behavior

Search is deterministic and local; it does not use an AI model or network
service. Results are ranked using:

1. exact name and alias matches;
2. prefix and phrase matches;
3. token overlap across names, aliases, descriptions, tags, and body regions;
4. bounded fuzzy matching for typing mistakes.

Examples include `thoughtful`, `hand on chin`, `akimbo`, `left hand raised`,
and `thnking`.

## Built-in poses

Built-in metadata is defined in:

```text
src/eric_motion_studio/resources/pose_definitions/builtins.json
```

Each entry references a reusable joint map in:

```text
src/eric_motion_studio/resources/gesture_stages/builtin_stages.json
```

Required metadata:

```text
id
name
source_pose
description
aliases
tags
body_regions
```

Set `mirror_arms` to `true` to generate a left/right mirrored built-in from an
existing source pose. IDs must be stable lowercase identifiers. Aliases should
describe natural phrases a user is likely to search.

After adding a built-in, run:

```text
.venv/bin/python -m pytest -q
.venv/bin/python -m eric_motion_studio --self-test
```

## Custom pose files

Custom poses are stored in the platform user-data `poses/` directory using the
versioned pose schema. Search metadata is stored with the joint snapshot:

```text
pose_id
pose_name
pose_description
pose_aliases
pose_tags
pose_body_regions
library_origin
joint_offsets_rad
```

Existing V1 pose files without search metadata remain readable. Their filename
is used as the display name.

Applying a pose never modifies a keyframe automatically. Keyframes capture a
snapshot of the previewed joints, so later pose-library changes cannot silently
change an existing motion.
