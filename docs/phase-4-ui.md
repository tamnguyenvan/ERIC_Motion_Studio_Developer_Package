# Phase 4 PySide6 UI

The Qt layer is now a composition shell over pure controllers and injected
services.

## Focused widgets

- motion metadata
- gesture definition library and prompt
- full 29-joint editor
- keyframe list and editing controls
- playback controls and timeline
- status, dirty-state, and simulation indicators

Widgets emit user-intent signals and render controller state. They do not read
or write files, launch processes, compile gestures, or own document state.

## Controllers and services

`DocumentController` owns lifecycle, selection, editing, undo/redo, persistence
coordination, and unsaved-change decisions. Separate controllers own gesture
authoring, local BrainOS export, and playback.

Filesystem repositories, the gesture compiler, playback output, dialogs, and
export are injected through protocols. Phase 5 can replace the null playback
output with runtime I/O without changing widgets.

The main window preserves standard New/Open/Save/Save As, Undo/Redo, Quit, and
playback shortcuts. Visible status text, dirty state, selection, generated
gesture application, save/export paths, and playback state are covered by
offscreen Qt tests.
