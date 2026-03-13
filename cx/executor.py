from __future__ import annotations

import os
import subprocess
import sys


def execute_rule(fd: int, cmd: str) -> None:
    """Run cmd in the shell, then wait for a keypress before returning."""
    print(f'\n$ {cmd}')
    try:
        subprocess.run(cmd, shell=True)
    except Exception as e:
        print(f'cx: error running command: {e}')
    print('\n[Press any key to return to cx...]', end='', flush=True)
    os.read(fd, 1)
