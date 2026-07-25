# Gesture command framework

ERIC Motion Studio uses a deterministic, data-driven command framework. It does
not use an AI model, embeddings, or an external language service.

## Resolution order

Commands pass through four layers:

1. **Aliases** — complete user-facing phrases attached to one gesture.
2. **Semantic grammar** — reusable action and effector vocabulary composed with
   typed slots such as side, direction, speed, intensity, hold, sequence, and
   neutral return.
3. **Triggers** — short, unambiguous commands such as `idle`, `stop`, or
   `farewell`.
4. **Suggestions** — deterministic similarity is used only after matching
   fails. Suggestions are shown to the user but are never executed
   automatically.

The resolver prefers exact and more-specific phrases. For example:

```text
idle         -> idle_pose
talking idle -> talking_idle
```

Tags are not command vocabulary. A tag such as `arm` or `full-body` is too broad
to execute safely.

## Add a synonym to an existing gesture

Edit:

```text
src/eric_motion_studio/resources/gesture_definitions/builtins.json
```

Use `aliases` for natural phrases:

```json
{
  "canonical_id": "idle_pose",
  "aliases": ["idle pose", "stand idle", "relaxed idle", "rest pose"],
  "triggers": ["idle", "rest", "relax", "standby"]
}
```

Use `triggers` only for short commands that unambiguously identify one gesture.
Do not duplicate the same normalized phrase in both fields.

No Python change is needed for an alias or trigger.

## Add a reusable action synonym

Edit:

```text
src/eric_motion_studio/resources/gesture_lexicon/builtins.json
```

Action groups contain equivalent verbs:

```json
{
  "actions": {
    "raise": ["raise", "lift", "elevate", "hoist"]
  }
}
```

Rules connect action groups and optional effectors to canonical gestures:

```json
{
  "canonical_id": "raise_arm",
  "actions": ["raise"],
  "effectors": ["arm"]
}
```

This automatically supports combinations such as `hoist left hand`, `hoist
right arm`, and speed/intensity modifiers without adding every full phrase.

Vocabulary phrases may belong to only one action group or effector group. The
loader rejects collisions.

## Add a new gesture

1. Add a validated definition to
   `resources/gesture_definitions/builtins.json`.
2. Reuse or add named poses and stages in
   `resources/gesture_stages/builtin_stages.json`.
3. Register a generator in `gestures/generators.py`. Prefer the existing
   stage-sequence generator when possible.
4. Add semantic vocabulary/rules only if compositional commands are required.
5. Add the canonical command, synonyms, short triggers, ambiguous cases, and
   unsupported cases to `tests/test_gesture_language.py`.
6. Run the command and MuJoCo audits.

## Verification commands

```bash
.venv/bin/python -m eric_motion_studio --audit-command "idle"
.venv/bin/python -m eric_motion_studio --audit-commands
.venv/bin/python -m eric_motion_studio --audit-mujoco-gestures
env QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
```

The command audit compiles and validates every alias and trigger. The MuJoCo
audit compiles one canonical command per implemented gesture, expands it to a
dense trajectory, and applies every frame to the packaged G1 MuJoCo model.

## Matching policy

- Exact and specific deterministic matches may execute.
- Equal candidates return an ambiguity error.
- Invalid or unsupported slots return a typed error.
- Similarity never causes execution; it only produces “Did you mean”
  suggestions.
- Existing aliases remain regression-tested to prevent compatibility loss.
