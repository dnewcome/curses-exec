from __future__ import annotations

import os
import sys


def main() -> None:
    if sys.stdin.isatty():
        print("cx: pipe input into cx, e.g.:  ps -ax | cx", file=sys.stderr)
        sys.exit(1)

    # Slurp stdin (the pipe) before we touch the terminal
    lines = sys.stdin.read().splitlines()
    if not lines:
        print("cx: no input", file=sys.stderr)
        sys.exit(1)

    # Late imports so config errors surface before curses hijacks the terminal
    from cx.config import load_config
    from cx.tui import run_tui

    rules = load_config()

    # Replace fd 0 with /dev/tty so curses (and sys.stdin reads in executor)
    # can read keyboard input even though we were launched from a pipe.
    tty_fd = os.open("/dev/tty", os.O_RDWR)
    os.dup2(tty_fd, 0)
    os.close(tty_fd)
    sys.stdin = open("/dev/tty", "r")

    run_tui(lines, rules)
