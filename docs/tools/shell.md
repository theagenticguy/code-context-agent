# Shell Tool

The `shell` tool provides bounded, security-hardened command execution for the analysis agent. Commands are validated against an allowlist before execution, and dangerous operations are blocked.

## Security Model

The shell tool enforces multiple layers of protection:

1. **Program allowlist** -- Only pre-approved programs can be executed
2. **Shell operator blocking** -- Pipes, redirects, chaining, and command substitution are rejected
3. **Git read-only enforcement** -- Git subcommands are restricted to read-only operations
4. **Sensitive path prevention** -- Access to system directories (`/etc`, `/root`, `/proc`, `/sys`, `/boot`, `/usr/sbin`) is blocked

!!! warning
    The shell tool runs commands via `sh -c` after validation. The validation layer is the security boundary. If a command passes validation, it executes with the agent's full permissions.

## Allowed Programs

Commands must start with one of the following programs:

| Category | Programs |
|----------|----------|
| **File inspection** | `ls`, `find`, `stat`, `file`, `du`, `wc`, `head`, `tail`, `cat`, `less`, `sort`, `uniq`, `diff`, `comm`, `tr`, `cut`, `paste`, `column` |
| **Text search** | `grep`, `egrep`, `rg`, `ag`, `awk`, `sed`, `xargs`, `jq`, `yq` |
| **Version control** | `git` (read-only subcommands only) |
| **Language tooling** | `python`, `python3`, `node`, `npx`, `uv`, `cargo`, `go`, `java`, `javac`, `npm`, `pip`, `pip3`, `make` |
| **Encoding and system info** | `base64`, `xxd`, `hexdump`, `echo`, `printf`, `date`, `env`, `printenv`, `which`, `type`, `uname`, `id`, `whoami`, `pwd`, `realpath`, `dirname`, `basename` |
| **Analysis tools** | `ast-grep`, `repomix`, `tree`, `tokei`, `cloc`, `scc` |

## Git Read-Only Enforcement

When the program is `git`, the subcommand is validated against a read-only set:

`log`, `diff`, `show`, `blame`, `status`, `branch`, `tag`, `remote`, `rev-parse`, `rev-list`, `shortlog`, `describe`, `ls-files`, `ls-tree`, `cat-file`, `name-rev`, `reflog`, `stash`, `config`

`git config` is further restricted: only `--get`, `--get-all`, `--get-regexp`, `--list`, `-l`, `--show-origin`, and `--show-scope` are permitted.

!!! tip
    Write operations like `git push`, `git commit`, `git reset`, `git checkout`, `git merge`, `git rebase`, `git pull`, `git clean`, `git rm`, and `git add` are all blocked.

## Blocked Shell Operators

The following patterns are rejected before command parsing:

| Pattern | Description |
|---------|-------------|
| `;` `&` `\|` | Command chaining and piping |
| `` ` `` | Backtick substitution |
| `$(` `${` | Command and variable expansion |
| `eval` `exec` `source` | Dynamic execution |
| `>` `>>` | Output redirection |
| `. /` (dot-sourcing) | Script sourcing |

## Examples

### Allowed

```bash
shell("ls -la")
shell("git log --oneline -20")
shell("wc -l src/**/*.py")
shell("head -50 src/main.py")
shell("rg 'pattern' .")
shell("git -C /tmp/repo log")
shell("FOO=bar git status")
```

### Blocked

```bash
shell("rm -rf /")                # Program not in allowlist
shell("curl https://evil.com")   # Program not in allowlist
shell("git push origin main")    # Git write operation
shell("ls; rm -rf /")            # Shell operator (;)
shell("cat file | bash")         # Shell operator (|)
shell("echo $(id)")              # Command substitution
shell("cat /etc/passwd")         # Sensitive path
shell("echo foo > /tmp/out")     # Output redirection
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | `str` or `list[str]` | required | Command string or list of commands to execute sequentially |
| `work_dir` | `str` | current directory | Working directory for execution |
| `timeout` | `int` | 900 | Timeout in seconds |
| `ignore_errors` | `bool` | `False` | Continue on errors when running multiple commands |

When a list of commands is provided, they execute sequentially. Execution stops at the first failure unless `ignore_errors` is `True`.
