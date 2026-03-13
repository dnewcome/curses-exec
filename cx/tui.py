from __future__ import annotations

import curses

from cx.config import Rule
from cx.executor import execute_rule
from cx.interpolate import interpolate


def run_tui(lines: list[str], rules: list[Rule]) -> None:
    curses.wrapper(_tui_main, lines, rules)


def _tui_main(stdscr, lines: list[str], rules: list[Rule]) -> None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected row
    curses.init_pair(2, curses.COLOR_RED, -1)                    # error status
    curses.init_pair(3, curses.COLOR_GREEN, -1)                  # ok status

    cursor = 0
    offset = 0
    status = ""
    status_attr = curses.A_NORMAL

    while True:
        h, w = stdscr.getmaxyx()
        list_h = h - 1  # bottom row is the status bar

        cursor = max(0, min(cursor, len(lines) - 1))
        if cursor < offset:
            offset = cursor
        if cursor >= offset + list_h:
            offset = cursor - list_h + 1

        stdscr.erase()

        for row in range(list_h):
            idx = offset + row
            if idx >= len(lines):
                break
            line = lines[idx]
            # Truncate to fit width (leave last column to avoid wrap artifacts)
            display = line[: w - 1].ljust(w - 1)
            attr = curses.color_pair(1) if idx == cursor else curses.A_NORMAL
            try:
                stdscr.addstr(row, 0, display, attr)
            except curses.error:
                pass  # terminal too small

        # Status bar
        pos = f" {cursor + 1}/{len(lines)}"
        status_line = (pos + "  " + status)[: w - 1].ljust(w - 1)
        try:
            stdscr.addstr(h - 1, 0, status_line, status_attr)
        except curses.error:
            pass

        stdscr.refresh()
        status = ""
        status_attr = curses.A_NORMAL

        ch = stdscr.getch()

        if ch == curses.KEY_RESIZE:
            continue
        elif ch in (ord("q"), 27):  # q or ESC
            break
        elif ch in (ord("j"), curses.KEY_DOWN):
            cursor = min(cursor + 1, len(lines) - 1)
        elif ch in (ord("k"), curses.KEY_UP):
            cursor = max(cursor - 1, 0)
        elif ch == ord("g"):
            cursor = 0
        elif ch == ord("G"):
            cursor = len(lines) - 1
        elif ch in (6, curses.KEY_NPAGE):   # Ctrl-F / Page Down
            cursor = min(cursor + list_h, len(lines) - 1)
        elif ch in (2, curses.KEY_PPAGE):   # Ctrl-B / Page Up
            cursor = max(cursor - list_h, 0)
        elif 32 <= ch < 127:
            pressed = chr(ch)
            current_line = lines[cursor]
            matching = _find_matching_rules(rules, pressed, current_line)

            if not matching:
                status = f"no rule for '{pressed}' on this line"
                status_attr = curses.color_pair(2)
            elif len(matching) == 1:
                rule, match = matching[0]
                cmd = interpolate(rule.command, current_line, match)
                execute_rule(stdscr, cmd)
                status = f"ran: {cmd}"
                status_attr = curses.color_pair(3)
            else:
                choice = _pick_rule_menu(stdscr, matching)
                if choice is not None:
                    rule, match = matching[choice]
                    cmd = interpolate(rule.command, current_line, match)
                    execute_rule(stdscr, cmd)
                    status = f"ran: {cmd}"
                    status_attr = curses.color_pair(3)


def _find_matching_rules(
    rules: list[Rule], key: str, line: str
) -> list[tuple[Rule, object]]:
    results = []
    for rule in rules:
        if rule.key == key:
            m = rule.pattern.search(line)
            if m:
                results.append((rule, m))
    return results


def _pick_rule_menu(stdscr, matching: list[tuple[Rule, object]]) -> int | None:
    """Overlay a small selection menu; return chosen index or None to cancel."""
    h, w = stdscr.getmaxyx()
    menu_h = min(len(matching) + 2, max(4, h // 3))
    top = h - menu_h
    win = curses.newwin(menu_h, w, top, 0)
    win.keypad(True)
    sel = 0

    while True:
        win.erase()
        try:
            win.addstr(0, 0, " Select action (j/k/Enter/Esc): "[: w - 1].ljust(w - 1), curses.A_BOLD)
        except curses.error:
            pass
        for i, (rule, _) in enumerate(matching):
            if i + 1 >= menu_h:
                break
            attr = curses.A_REVERSE if i == sel else curses.A_NORMAL
            label = f"  {rule.description}"[: w - 1].ljust(w - 1)
            try:
                win.addstr(i + 1, 0, label, attr)
            except curses.error:
                pass
        win.refresh()

        ch = win.getch()
        if ch in (ord("j"), curses.KEY_DOWN) and sel < len(matching) - 1:
            sel += 1
        elif ch in (ord("k"), curses.KEY_UP) and sel > 0:
            sel -= 1
        elif ch in (10, 13, curses.KEY_ENTER):
            del win
            return sel
        elif ch == 27:
            del win
            return None
