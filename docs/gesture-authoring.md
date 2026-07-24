# Gesture Authoring

Built-in gesture definitions live in
`src/eric_motion_studio/resources/gesture_definitions/builtins.json`.

Each definition supplies a canonical ID, aliases, supported slots, defaults,
constraints, tags, and a generator ID. Add a synonym by editing the aliases for
the existing definition. Add a reusable pose or stage in the corresponding
resource JSON. A procedural gesture requires a generator implementation and one
registry entry; parser conditionals are not supported.

Validate changes with:

```text
.venv/bin/eric-motion-studio --audit-command "wave right hand"
.venv/bin/eric-motion-studio --audit-commands
```

Generated frames are normalized, compiled, joint-limit checked, and passed
through semantic and safety validators before they reach the editor or viewer.
