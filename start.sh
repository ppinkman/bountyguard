#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
task_python=".venv/bin/python"
if [[ ! -x "$task_python" && -f .venv/Scripts/python.exe ]]; then
    task_python=".venv/Scripts/python.exe"
fi
if [[ ! -f "$task_python" ]]; then
    echo "Create .venv and install requirements.txt first." >&2
    exit 1
fi
exec "$task_python" -m bountyguard serve --port "${1:-8766}"
