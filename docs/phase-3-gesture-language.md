# Phase 3 Gesture Language

Gesture parsing and generation are now data-driven and pure Python.

## Pipeline

1. Load and validate packaged gesture definitions and reusable stage data.
2. Normalize command text and match exact or contained alias phrases.
3. Extract typed side, direction, speed, intensity, hold, sequence, and
   neutral-return slots.
4. Return an explicit success, ambiguity, unsupported-gesture, or invalid-slot
   resolution.
5. Dispatch through the generator registry.
6. Validate joint limits, amplitude, trajectory, balance, collision heuristics,
   semantic side, and exact neutral return.

Definitions under `resources/gesture_definitions/` own canonical IDs, aliases,
slots, defaults, tags, generator IDs, and constraints. Adding an alias requires
only a data edit. Poses, sequences, and structured-command clause patterns live
under `resources/gesture_stages/`.

Built-in generators cover waves, talking idle, thinking, head scratching,
raising and lowering arms, hand-to-chest motion, two-arm presentations,
welcoming sweeps, neutral reset, and structured compound full-body commands.
Generated motions use fixed metadata timestamps and deterministic algorithms.

Every supported legacy alias resolves and compiles successfully. Unknown
commands remain unsupported, while malformed definitions and unsafe generated
motions fail at explicit boundaries.
