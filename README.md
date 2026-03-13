# cx — curses-exec

`cx` is a terminal pager with vim-style navigation that can execute commands against selected lines. Pipe any command's output into it, navigate with `j`/`k`, press a configured key on a line, and a shell command runs — with the matched text interpolated in.

```
ps -ax | cx
```

Press `k` on a process line → `kill <pid>`. Press `K` → `kill -9 <pid>`.

The key-to-command mappings live in `~/.cx.yaml`. One config file handles all your use cases: process management, git log navigation, Docker container control, log inspection, and anything else that fits the pattern of "pick a line, do something with it."


## Installation

```sh
pipx install cx
```

Or from source:

```sh
git clone <repo>
cd cx
pipx install .
```

`cx` requires Python 3.10+ and `PyYAML`. `pipx` handles the dependency automatically.

To install without `pipx`:

```sh
python3 -m venv ~/.venv/cx
~/.venv/cx/bin/pip install .
ln -s ~/.venv/cx/bin/cx ~/.local/bin/cx
```


## Quick start

Copy the example config to your home directory:

```sh
cp cx.yaml.example ~/.cx.yaml
```

Then pipe something into `cx`:

```sh
ps -ax | cx
```

Navigate with `j`/`k`, press `k` to send SIGTERM to the selected process, `K` for SIGKILL. Press `q` to quit.


## How it works

1. `cx` reads all of stdin into memory.
2. It opens an interactive curses screen listing every line.
3. You navigate to a line and press a key.
4. `cx` scans `~/.cx.yaml` for rules whose `pattern` matches the selected line and whose `key` matches the key you pressed.
5. If a rule matches, it interpolates the command template with the regex capture groups and executes it in your shell.
6. Command output is shown directly in the terminal. Press any key to return to the list.

If more than one rule matches the key on the current line, a small selection menu appears so you can choose which action to run.


## Navigation

| Key | Action |
|-----|--------|
| `j` / `↓` | Move down one line |
| `k` / `↑` | Move up one line |
| `g` | Jump to first line |
| `G` | Jump to last line |
| `Ctrl-F` / `Page Down` | Page down |
| `Ctrl-B` / `Page Up` | Page up |
| `q` / `Esc` | Quit |

Any other key triggers rule matching against the current line.


## Config file

`cx` reads `~/.cx.yaml` on startup. If the file does not exist, `cx` runs in read-only navigation mode (no actions).

### Rule structure

```yaml
rules:
  - pattern: '<regex>'
    key: '<single character>'
    command: '<shell command template>'
    description: '<shown in menus>'   # optional
```

- **pattern** — A Python regular expression. `cx` uses `re.search`, so the pattern does not need to match the whole line. Use capture groups `(...)` or named groups `(?P<name>...)` to extract the parts you need.
- **key** — Exactly one character. Case-sensitive. `k` and `K` are distinct.
- **command** — A shell command. Passed to `/bin/sh -c`. May use pipes, redirects, and any shell syntax.
- **description** — Optional. Displayed in the multi-rule selection menu and in the status bar. Falls back to the `command` string if omitted.

Multiple rules may share the same `key`. When you press that key, all rules whose `pattern` matches the current line are collected. If there is exactly one match, the command runs immediately. If there are multiple matches, a menu lets you choose.


## Template variables

Within the `command` string, the following placeholders are replaced before the command is executed:

| Placeholder | Value |
|-------------|-------|
| `{line}` | The full text of the selected line |
| `{0}` | The substring matched by `pattern` (the full regex match) |
| `{1}`, `{2}`, ... | Capture group 1, 2, ... from `pattern` |
| `{name}` | Named capture group `(?P<name>...)` |

**Note:** Values are substituted as plain strings with no shell escaping. If a captured value might contain spaces or special characters, quote the placeholder in the command:

```yaml
command: 'grep -r "{1}" /var/log'
```


## Examples

### Process management (`ps -ax | cx`)

```yaml
rules:
  - pattern: '^\s*(\d+)'
    key: k
    command: 'kill {1}'
    description: 'Send SIGTERM'

  - pattern: '^\s*(\d+)'
    key: K
    command: 'kill -9 {1}'
    description: 'Send SIGKILL'

  - pattern: '^\s*(\d+)'
    key: i
    command: 'ps -p {1} -o pid,ppid,user,%cpu,%mem,vsz,rss,stat,start,time,command | less'
    description: 'Inspect process'
```

### Git log (`git log --oneline | cx`)

```yaml
rules:
  - pattern: '^([0-9a-f]{7,40})'
    key: d
    command: 'git show {1} | less'
    description: 'Show diff'

  - pattern: '^([0-9a-f]{7,40})'
    key: c
    command: 'git checkout {1}'
    description: 'Checkout'

  - pattern: '^([0-9a-f]{7,40})'
    key: r
    command: 'git rebase -i {1}~1'
    description: 'Interactive rebase from here'

  - pattern: '^([0-9a-f]{7,40})'
    key: p
    command: 'git cherry-pick {1}'
    description: 'Cherry-pick'
```

### Docker containers (`docker ps | cx`)

```yaml
rules:
  - pattern: '^([0-9a-f]{12})'
    key: s
    command: 'docker stop {1}'
    description: 'Stop container'

  - pattern: '^([0-9a-f]{12})'
    key: x
    command: 'docker rm -f {1}'
    description: 'Force remove container'

  - pattern: '^([0-9a-f]{12})'
    key: l
    command: 'docker logs --tail 100 -f {1}'
    description: 'Follow logs'

  - pattern: '^([0-9a-f]{12})'
    key: e
    command: 'docker exec -it {1} /bin/sh'
    description: 'Open shell'
```

### Network connections (`ss -tulpn | cx` or `netstat -tulpn | cx`)

```yaml
rules:
  - pattern: ':(\d+)\s'
    key: o
    command: 'curl -s http://localhost:{1} | head -20'
    description: 'curl localhost port'
```

### File listing (`ls -la | cx` or `find . -name "*.log" | cx`)

```yaml
rules:
  - pattern: '(\S+)$'
    key: e
    command: '$EDITOR {1}'
    description: 'Open in editor'

  - pattern: '(\S+)$'
    key: l
    command: 'less {1}'
    description: 'Page file'

  - pattern: '(\S+)$'
    key: d
    command: 'rm {1}'
    description: 'Delete file'
```

### Log files (`tail -n 200 /var/log/syslog | cx`)

```yaml
rules:
  - pattern: '\b([a-zA-Z0-9_-]+)\[(\d+)\]'
    key: f
    command: 'grep "{1}" /var/log/syslog | less'
    description: 'Filter log by process name'
```

### System services (`systemctl list-units --type=service | cx`)

```yaml
rules:
  - pattern: '([\w@.-]+\.service)'
    key: r
    command: 'sudo systemctl restart {1}'
    description: 'Restart service'

  - pattern: '([\w@.-]+\.service)'
    key: j
    command: 'journalctl -u {1} -n 50 | less'
    description: 'View journal'

  - pattern: '([\w@.-]+\.service)'
    key: s
    command: 'sudo systemctl stop {1}'
    description: 'Stop service'
```

### Named capture groups

Named groups make commands more readable when patterns are complex:

```yaml
  - pattern: '(?P<host>[\w.-]+)\s+(?P<port>\d+)'
    key: c
    command: 'ssh {host} -p {port}'
    description: 'SSH to host'
```


## Shell aliases

Short aliases make `cx` feel like a first-class command:

```sh
# ~/.bashrc or ~/.zshrc
alias psk='ps -ax | cx'
alias gll='git log --oneline | cx'
alias dps='docker ps | cx'
alias ssn='ss -tulpn | cx'
```


## Tips

**Long lines:** `cx` truncates lines at the terminal width for display but uses the full original line for pattern matching and `{line}` substitution.

**Interactive commands:** Commands like `vim`, `less`, `docker exec -it`, and `ssh` require a real terminal. They work correctly because `cx` suspends the curses display, hands the terminal back to the shell, and resumes only after the command exits.

**Chaining:** Because `cx` is a passive recipient of stdin, it composes freely with any command pipeline:

```sh
ps -ax | grep python | cx
find /var/log -name '*.log' -newer /tmp/marker | cx
kubectl get pods -A | grep CrashLoop | cx
```

**Multiple configs:** The config path is always `~/.cx.yaml`. To switch between different rule sets, use symlinks or a shell function that temporarily copies a file.

**Escaping braces:** To include a literal `{` or `}` in a command, the current interpolation engine treats `{unknown_key}` as a pass-through (the placeholder is left unchanged). Name your capture groups to avoid collisions with shell syntax.


## Config reference

Full annotated example (`cx.yaml.example` in the source tree):

```yaml
rules:
  - pattern: '<python regex>'     # required; re.search is used
    key: '<char>'                  # required; one character, case-sensitive
    command: '<shell command>'     # required; passed to sh -c
    description: '<label>'         # optional; shown in menus and status bar
```

Errors in the config (invalid regex, multi-character key) are reported on startup before the TUI opens, so you see them immediately.


## License

MIT
