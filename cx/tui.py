from __future__ import annotations

import fcntl
import os
import select
import signal
import struct
import sys
import termios
import tty

from cx.config import Rule
from cx.executor import execute_rule
from cx.interpolate import interpolate

CSI = '\033['


def run_tui(lines: list[str], rules: list[Rule]) -> None:
    tty_in = open('/dev/tty', 'rb', buffering=0)
    tty_out = open('/dev/tty', 'wb', buffering=0)
    fd = tty_in.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        tty_out.write(b'\033[?25l')   # hide cursor
        tty_out.flush()
        _run_inline(lines, rules, fd, tty_in, tty_out, old_attrs)
    finally:
        tty_out.write(b'\033[?25h')   # show cursor
        tty_out.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        tty_in.close()
        tty_out.close()


def _get_size(fd: int) -> tuple[int, int]:
    buf = fcntl.ioctl(fd, termios.TIOCGWINSZ, b'\x00' * 8)
    rows, cols = struct.unpack('hh', buf[:4])
    return rows, cols


def _read_key(fd: int, tty_in) -> str:
    b = tty_in.read(1)
    if b == b'\x1b':
        if not select.select([fd], [], [], 0.05)[0]:
            return 'esc'
        b2 = tty_in.read(1)
        if b2 != b'[':
            return 'esc'
        if not select.select([fd], [], [], 0.05)[0]:
            return 'esc'
        b3 = tty_in.read(1)
        if b3 == b'A':
            return 'up'
        if b3 == b'B':
            return 'down'
        if b3 in (b'5', b'6'):
            if select.select([fd], [], [], 0.05)[0]:
                tty_in.read(1)  # consume trailing ~
            return 'page_up' if b3 == b'5' else 'page_down'
        return 'esc'
    if b == b'\x03':   # Ctrl-C
        return 'quit'
    if b == b'\x06':   # Ctrl-F
        return 'page_down'
    if b == b'\x02':   # Ctrl-B
        return 'page_up'
    if b in (b'\r', b'\n'):
        return 'enter'
    if b and 32 <= b[0] < 127:
        return chr(b[0])
    return ''


def _reserve_space(tty_out, fd, tty_in, ui_h: int, term_h: int) -> None:
    """
    Anchor the UI to the bottom of the terminal regardless of current cursor
    position. Moves to the last row first, scrolls ui_h-1 lines to make room,
    then backs the cursor up to the UI top row.
    """
    # Jump to the last row so scrolling is always relative to the bottom.
    tty_out.write(f'{CSI}{term_h};1H'.encode())
    if ui_h > 1:
        tty_out.write(('\r\n' * (ui_h - 1)).encode())
        tty_out.write(f'{CSI}{ui_h - 1}A\r'.encode())
    else:
        tty_out.write(b'\r')
    tty_out.flush()


def _draw(tty_out, lines, cursor, offset, ui_h, term_w, status, status_attr) -> None:
    """Render the full UI. Cursor must be at UI row 0 col 0; restored there after."""
    list_h = ui_h - 1
    n = len(lines)
    out = []

    for row in range(list_h):
        out.append(f'{CSI}2K')
        idx = offset + row
        if idx < n:
            line = lines[idx][:term_w - 1]
            if idx == cursor:
                out.append(f'{CSI}7m{line:<{term_w - 1}}{CSI}m')
            else:
                out.append(line)
        out.append('\r\n')

    # Status bar (no trailing newline so we don't scroll past the bottom)
    pos = f' {cursor + 1}/{n}'
    status_line = (pos + '  ' + status)[:term_w - 1]
    color = (f'{CSI}31m' if status_attr == 'error'
             else f'{CSI}32m' if status_attr == 'ok'
             else '')
    reset = f'{CSI}m' if color else ''
    out.append(f'{CSI}2K{color}{status_line}{reset}')

    # Return cursor to UI row 0
    if ui_h > 1:
        out.append(f'{CSI}{ui_h - 1}A')
    out.append('\r')

    tty_out.write(''.join(out).encode())
    tty_out.flush()


def _run_inline(lines, rules, fd, tty_in, tty_out, old_attrs) -> None:
    n = len(lines)
    term_h, term_w = _get_size(fd)
    ui_h = min(n + 1, term_h)   # list rows + 1 status bar
    list_h = ui_h - 1

    cursor = n - 1               # start focused on last item
    offset = max(0, cursor - list_h + 1)
    status = ''
    status_attr = 'normal'

    resize_flag = [False]
    orig_sigwinch = signal.getsignal(signal.SIGWINCH)

    def handle_sigwinch(sig, frame):
        resize_flag[0] = True

    signal.signal(signal.SIGWINCH, handle_sigwinch)
    _reserve_space(tty_out, fd, tty_in, ui_h, term_h)

    try:
        while True:
            if resize_flag[0]:
                resize_flag[0] = False
                term_h, term_w = _get_size(fd)
                ui_h = min(n + 1, term_h)
                list_h = ui_h - 1

            cursor = max(0, min(cursor, n - 1))
            if cursor < offset:
                offset = cursor
            if cursor >= offset + list_h:
                offset = cursor - list_h + 1

            _draw(tty_out, lines, cursor, offset, ui_h, term_w, status, status_attr)
            status = ''
            status_attr = 'normal'

            key = _read_key(fd, tty_in)

            if key in ('q', 'esc', 'quit'):
                break
            elif key in ('j', 'down'):
                cursor = min(cursor + 1, n - 1)
            elif key in ('k', 'up'):
                cursor = max(cursor - 1, 0)
            elif key == 'g':
                cursor = 0
            elif key == 'G':
                cursor = n - 1
            elif key == 'page_down':
                cursor = min(cursor + list_h, n - 1)
            elif key == 'page_up':
                cursor = max(cursor - list_h, 0)
            elif key and len(key) == 1:
                current_line = lines[cursor]
                matching = _find_matching_rules(rules, key, current_line)
                if not matching:
                    status = f"no rule for '{key}' on this line"
                    status_attr = 'error'
                elif len(matching) == 1:
                    rule, match = matching[0]
                    cmd = interpolate(rule.command, current_line, match)
                    _run_command(tty_out, fd, old_attrs, ui_h, cmd)
                    term_h, term_w = _get_size(fd)
                    ui_h = min(n + 1, term_h)
                    list_h = ui_h - 1
                    _reserve_space(tty_out, fd, tty_in, ui_h, term_h)
                    status = f'ran: {cmd}'
                    status_attr = 'ok'
                else:
                    choice = _pick_menu(tty_out, tty_in, fd, lines, cursor, offset,
                                        ui_h, term_w, matching)
                    if choice is not None:
                        rule, match = matching[choice]
                        cmd = interpolate(rule.command, current_line, match)
                        _run_command(tty_out, fd, old_attrs, ui_h, cmd)
                        term_h, term_w = _get_size(fd)
                        ui_h = min(n + 1, term_h)
                        list_h = ui_h - 1
                        _reserve_space(tty_out, fd, tty_in, ui_h, term_h)
                        status = f'ran: {cmd}'
                        status_attr = 'ok'
    finally:
        signal.signal(signal.SIGWINCH, orig_sigwinch)
        # Clear the UI area; cursor remains at UI top for the shell prompt
        tty_out.write(f'{CSI}J'.encode())
        tty_out.flush()


def _run_command(tty_out, fd, old_attrs, ui_h, cmd) -> None:
    """Leave TUI, run cmd, wait for keypress, then re-enter raw mode."""
    # Move to bottom of UI and clear it so command output starts cleanly
    if ui_h > 1:
        tty_out.write(f'{CSI}{ui_h - 1}B\r'.encode())
    tty_out.write(f'{CSI}J'.encode())
    tty_out.write(b'\033[?25h')   # show cursor while command runs
    tty_out.flush()
    termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
    execute_rule(fd, cmd)
    tty.setraw(fd)
    tty_out.write(b'\033[?25l')   # hide cursor again
    tty_out.flush()


def _find_matching_rules(rules, key, line):
    results = []
    for rule in rules:
        if rule.key == key:
            m = rule.pattern.search(line)
            if m:
                results.append((rule, m))
    return results


def _pick_menu(tty_out, tty_in, fd, lines, cursor, offset,
               ui_h, term_w, matching) -> int | None:
    """Overlay a selection menu on the list area; return chosen index or None."""
    list_h = ui_h - 1
    if list_h < 2:
        return None  # no space for header + at least one item

    n = len(lines)
    menu_h = min(len(matching) + 1, list_h)   # header row + item rows
    if menu_h < 2:
        return None
    menu_start = list_h - menu_h   # first list row occupied by the menu

    sel = 0

    while True:
        out = []

        for row in range(list_h):
            out.append(f'{CSI}2K')
            if row >= menu_start:
                menu_row = row - menu_start
                if menu_row == 0:
                    header = ' Select action (j/k/Enter/Esc): '[:term_w - 1].ljust(term_w - 1)
                    out.append(f'{CSI}1m{header}{CSI}m')
                else:
                    i = menu_row - 1
                    if i < len(matching):
                        rule, _ = matching[i]
                        attr = f'{CSI}7m' if i == sel else ''
                        reset = f'{CSI}m' if i == sel else ''
                        label = f'  {rule.description}'[:term_w - 1].ljust(term_w - 1)
                        out.append(f'{attr}{label}{reset}')
            else:
                idx = offset + row
                if idx < n:
                    line = lines[idx][:term_w - 1]
                    if idx == cursor:
                        out.append(f'{CSI}7m{line:<{term_w - 1}}{CSI}m')
                    else:
                        out.append(line)
            out.append('\r\n')

        # Status bar
        pos = f' {cursor + 1}/{n}'
        status_line = f'{pos}  Select action'[:term_w - 1]
        out.append(f'{CSI}2K{status_line}')

        # Return cursor to UI row 0
        if ui_h > 1:
            out.append(f'{CSI}{ui_h - 1}A')
        out.append('\r')

        tty_out.write(''.join(out).encode())
        tty_out.flush()

        key = _read_key(fd, tty_in)
        if key in ('j', 'down') and sel < len(matching) - 1:
            sel += 1
        elif key in ('k', 'up') and sel > 0:
            sel -= 1
        elif key == 'enter':
            return sel
        elif key in ('esc', 'quit'):
            return None
