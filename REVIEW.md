# Review Findings

## P1: Preserve frame timing when converting trajectories

**Location:** `src/eric_motion_studio/domain/operations.py:129-132`

For standard 30 FPS playback plans, `keyframes_from_trajectory()` converts the
approximately 33 ms frame interval to the 100 ms editor keyframe minimum.
Converting a gesture to keyframes and back therefore makes it roughly three
times slower.

Preserve trajectory timing during conversion instead of applying the editor
keyframe minimum to every dense frame.

## P2: Validate gesture frame profiles before labeling values

**Location:** `src/eric_motion_studio/infrastructure/formats.py:404-408`

When gesture frames use a profile other than the serializer's configured
profile, configured joint names are paired with raw values ordered by the
frame's profile. A reordered profile can therefore produce a valid-looking file
whose joint values are silently assigned to the wrong joints on reload.

Reject profile mismatches before serialization, or derive joint names and values
from the same profile.

## P2: Enforce BrainOS-only schema constraints

**Location:** `src/eric_motion_studio/infrastructure/formats.py:430-436`

BrainOS payloads with a missing `version` or `simulation_only: false` are
delegated to `AnimationSerializer`, which permits legacy animations without a
version and accepts either boolean simulation flag. This contradicts the
packaged BrainOS schema, which requires version 1 and `simulation_only: true`.

Validate these constraints before delegation and prevent serialization with a
false simulation flag.

## P2: Reject non-integer keyframe durations

**Location:** `src/eric_motion_studio/infrastructure/formats.py:169-174`

Missing, numeric-string, floating-point, and boolean `duration_ms` values are
currently defaulted or coerced and then clamped, although the V1 schema requires
an integer field. Malformed animation payloads can therefore pass validation
with altered timing.

Require a present, non-boolean integer before constructing the keyframe.
