# Review Findings

## P2: Remove workstation-specific model paths

**Location:** `src/eric_motion_studio/resources/animations/conversational_talking.json:5`

All three bundled animations embed the same
`/Users/martinnicholas/Desktop/.../scene_29dof.xml` model path. Outside that
workstation, consumers that resolve or preserve the `model` field receive a
nonexistent path instead of the configured or packaged model, breaking package
portability.

Use a portable model identifier or package-relative reference in each animation
payload.

Affected resources:

- `conversational_talking.json`
- `thinking_hand_on_chin.json`
- `scratch_head.json`
