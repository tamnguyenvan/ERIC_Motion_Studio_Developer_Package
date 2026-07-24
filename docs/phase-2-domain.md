# Phase 2 Domain and File Formats

The package now exposes a pure, immutable domain layer:

- `JointValues`, `Keyframe`, `Motion`, `Pose`, `Gesture`
- `TrajectoryFrame`, `PlaybackPlan`, `PlaybackState`
- editing, cloning, clamping, retiming, interpolation, and dense trajectory
  operations
- one `UNITREE_G1` profile containing the canonical 29-joint order, conservative
  limits, groups, model ID, and display name

`eric_motion_studio.infrastructure.formats` provides animation, pose, gesture,
and local BrainOS export serializers and repositories. Each repository validates
its versioned schema before creating domain objects and writes JSON atomically.
The corresponding JSON Schema documents are packaged under
`resources/schemas/`.

Legacy animation files that omit the explicit `version` field are accepted as
animation V1 and upgraded on save. Partial 17-joint editor files are completed
with neutral values for the full 29-joint profile. Unknown joints, malformed
types, mismatched frame counts or durations, and incompatible model profiles
are rejected at the repository boundary.

The domain and format modules import without PySide6 or MuJoCo.
