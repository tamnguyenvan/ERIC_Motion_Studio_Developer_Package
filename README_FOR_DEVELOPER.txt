ERIC Motion Studio

Simulation only.

Environment:
- macOS
- Python 3.11
- MuJoCo
- PySide6
- Unitree G1 simulation

No physical robot.
No BrainOS.
No DDS.
No SDK2.

Current issue:

The application launches correctly.

Existing gestures work.

Commands such as:

- raise left hand
- raise right hand
- lift left hand
- lift right hand

currently produce:

MOTION_PARSE_FAILED
NO_MOTION_GENERATED

Requested work:

1. Confirm the launcher is using the correct source file.
2. Remove duplicate-file confusion.
3. Extend the natural-language motion parser.
4. Implement any missing motion routines.
5. Test all changes in MuJoCo.
6. Preserve existing functionality.
7. If practical, leave the project easier to maintain.
