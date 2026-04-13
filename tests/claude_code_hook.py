#!/usr/bin/env python3
"""
Claude Code Hook - Automatic ContextWolf Integration
Can be integrated into Claude Code's hook system.

Uses the globally installed 'cm' command (no hardcoded paths).
"""

import sys
import subprocess
from pathlib import Path


def on_file_edit(file_path: str, action: str):
    """Called after every file change."""
    project = Path.cwd().name
    file_name = Path(file_path).name

    descriptions = {
        'create': f"Created new file {file_name}",
        'edit': f"Modified {file_name}",
        'delete': f"Deleted {file_name}"
    }

    description = descriptions.get(action, f"{action} {file_name}")

    cmd = ["cm", "save", description, "--type", "code", "--project", project]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Auto-saved to ContextWolf: {description}")
        else:
            print(f"⚠️ ContextWolf error: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Hook error: {e}")


def on_command_run(command: str, output: str, exit_code: int):
    """Called after every executed command."""
    project = Path.cwd().name

    output_short = output[:200] + "..." if len(output) > 200 else output

    description = f"Command: {command} | Exit: {exit_code}"
    if exit_code == 0 and output_short:
        description += f" | Output: {output_short}"

    cmd = ["cm", "save", description, "--type", "command", "--project", project]

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    except Exception:
        pass  # Silently fail to not interrupt workflow


if __name__ == "__main__":
    if len(sys.argv) > 1:
        hook_type = sys.argv[1]

        if hook_type == "file-edit" and len(sys.argv) >= 4:
            on_file_edit(sys.argv[2], sys.argv[3])
        elif hook_type == "command" and len(sys.argv) >= 4:
            on_command_run(sys.argv[2], sys.argv[3], int(sys.argv[4]))
        else:
            print(f"Usage: {sys.argv[0]} [file-edit|command] [args...]")
