from __future__ import annotations

import curses
import subprocess
import sys


def execute_rule(stdscr, cmd: str, exit: bool = False) -> None:
    """Suspend curses, run cmd in the shell, optionally wait for keypress, resume curses."""
    curses.endwin()
    print(f"\n$ {cmd}")
    try:
        subprocess.run(cmd, shell=True)
    except Exception as e:
        print(f"cx: error running command: {e}")
    if not exit:
        print("\n[Press any key to return to cx...]", end="", flush=True)
        sys.stdin.read(1)
    stdscr.refresh()
