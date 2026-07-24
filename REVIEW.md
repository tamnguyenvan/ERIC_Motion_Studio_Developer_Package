# Review Findings

## P1: Stop resetting the description cursor on every edit

**Location:** `src/eric_motion_studio/ui/widgets/motion_metadata.py:35`

Each `textChanged` signal immediately updates the document. The resulting state
publication calls `setPlainText()` on the same editor, resetting its cursor to
position zero. Continued typing is prepended, so `abc` can become `cba`, and
every character also creates a separate undo entry.

Commit description metadata when editing finishes, or preserve the cursor while
rendering state.

## P2: Preserve the loop flag during playback

**Location:** `src/eric_motion_studio/ui/controllers.py:432-434`

`PlaybackController.set_motion()` discards `motion.loop`, and reaching the final
frame always stops playback. Consequently, checking “Loop playback” or loading a
motion with `loop=True` has no effect.

Preserve the motion's loop setting and restart the plan after the final frame
when looping is enabled.

## P2: Recompute dirty state when undo reaches the saved revision

**Location:** `src/eric_motion_studio/ui/controllers.py:253-256`

Undo and redo unconditionally set `dirty=True`. When undo restores the initial
or most recently saved motion, the UI therefore keeps its unsaved marker and
prompts to save on close even though the document matches the persisted
baseline.

Derive dirty state from the current motion versus the saved revision after both
undo and redo.

## P2: Apply the initial frame when playback starts

**Location:** `src/eric_motion_studio/ui/controllers.py:381-384`

Starting playback from frame zero changes controller state but does not send
frame zero to `PlaybackOutput`. The first output call occurs only after
advancing, so startup and playback after `stop()` begin from the second
trajectory sample.

Apply the initial frame when playback starts from frame zero.
