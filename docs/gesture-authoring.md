# Gesture Authoring

Built-in gesture definitions live in
`src/eric_motion_studio/resources/gesture_definitions/builtins.json`. The
deterministic action/effector lexicon lives in
`src/eric_motion_studio/resources/gesture_lexicon/builtins.json`.

Each definition supplies a canonical ID, idiomatic phrases, supported slots,
defaults, constraints, tags, and a generator ID. Add action synonyms such as
`elevate` or body-part synonyms such as `hand` in the lexicon; every compatible
combination is then recognized without adding full command phrases. Reserve
definition aliases for named gestures and idioms such as `thumbs up` or
`hands on hips`.

Add a reusable pose or stage in the corresponding resource JSON. A procedural
gesture requires a generator implementation and one registry entry. Generators
consume typed semantic commands and must not inspect raw command text.

Validate changes with:

```text
.venv/bin/eric-motion-studio --audit-command "wave right hand"
.venv/bin/eric-motion-studio --audit-commands
```

Generated frames are normalized, compiled, joint-limit checked, and passed
through semantic and safety validators before they reach the editor or viewer.

Every definition also appears as a read-only built-in in the Motion Library.
Select a built-in and choose **Duplicate** to create an editable custom copy
under `motions/`. The copy is added to the library and opened immediately.
Use the normal **Save** command while editing. Custom motions can be opened,
duplicated, or deleted; built-ins remain read-only. No approval step is needed.

Do not manually maintain a second built-in dense gesture file. The definition,
lexicon, and stages are the canonical built-in source.
