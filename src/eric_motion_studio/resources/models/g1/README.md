# Unitree G1 Model

This directory is the complete immutable Unitree G1 29-DoF runtime model:

- `scene_29dof.xml` is the configured viewer scene;
- `g1_29dof.xml` defines the robot, joints, and actuators; and
- `meshes/` contains every mesh referenced by the model.

The package and installed wheel resolve these files relative to this directory.
No runtime fallback to the legacy tree is supported.
