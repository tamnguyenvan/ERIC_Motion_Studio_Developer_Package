# Resources

Immutable runtime assets are packaged under
`src/eric_motion_studio/resources/`. The active layout contains:

- three built-in animation files;
- three saved gesture files;
- gesture definitions and reusable stage data;
- versioned JSON schemas; and
- the complete Unitree G1 29-DoF MuJoCo scene, model, and meshes.

These are package inputs only. Mutable motions, exports, logs, and viewer IPC are
resolved through `Settings` and must never be stored in either resource tree or
the read-only `codebase/` backup.
