# Testing

Run the complete local gate from the repository root:

```text
.venv/bin/ruff format --check src tests tools
.venv/bin/ruff check src tests tools
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
.venv/bin/eric-motion-studio --headless --no-console-log
.venv/bin/eric-motion-studio --self-test
.venv/bin/eric-motion-studio --audit-commands
.venv/bin/python tools/cutover_audit.py
.venv/bin/eric-motion-studio-viewer --self-test
.venv/bin/python tools/release_audit.py
```

The Qt suite is offscreen-capable. The viewer self-test loads the packaged G1
model without opening a window. CI runs the same gates on Python 3.11.
