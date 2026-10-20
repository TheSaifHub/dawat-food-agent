"""Dawat project guard: Claude Code hook enforcing the CLAUDE.md safety rules.

Wired up in .claude/settings.json. Reads the hook event JSON on stdin.

  PreToolUse    → denies the tool call (JSON permissionDecision "deny") when it:
                  1. runs git or gh                      (no-git rule)
                  2. writes/edits/deletes under data/raw/ (raw data is read-only)
                  3. writes content containing a secret   (no secrets in files)
                  4. reads or writes a real .env file     (secrets stay out of context)
                → asks Saif first (permissionDecision "ask") when it:
                  6. runs something against a database: migrate.py --apply (not --local),
                     load_db.py or a db_write_* script, or SQL DELETE FROM / TRUNCATE / DROP
                     TABLE|SCHEMA|DATABASE. Text being written or searched for (Add-Content,
                     Set-Content, Out-File, echo, heredocs to cat, grep patterns) doesn't count.
  SessionStart  → 5. injects the session-control reminder.

Standard library only, so it works without the project venv.
Pattern-based: it stops honest mistakes, not a determined adversary.
"""

import json
import os
import re
import sys

# ─── 1. git ────────────────────────────────────────────────────────────
# `git`/`gh` as a command: at the start or after a separator (; & | && || ( ` $( newline),
# optionally path-qualified or quoted. `.gitignore` or `digit` never match.
GIT_COMMAND = re.compile(
    r"""(?:^|[;&|({`\n]|\$\()\s*(?:sudo\s+|env\s+|command\s+|time\s+)?"""
    r"""["']?(?:[\w:.~-]*[\\/])*(?:git|gh)(?:\.exe)?["']?(?=\s|$|[;&|)])""",
    re.IGNORECASE,
)
GIT_VIA_SUBPROCESS = re.compile(r"""["'](?:git|gh)(?:\.exe)?["']\s*[,\]]""", re.IGNORECASE)

# ─── 2. data/raw ───────────────────────────────────────────────────────
RAW_PATH = re.compile(r"data[\\/]+raw(?:[\\/]|$|[\s'\"])", re.IGNORECASE)
RAW_MUTATING = [
    re.compile(
        r"(?:^|[\s;&|(`])(?:rm|rmdir|mv|truncate|shred|unlink|touch|tee|dd|del|erase|ren|rename|"
        r"remove-item|ri|move-item|rename-item|set-content|add-content|out-file|clear-content|"
        r"new-item|copy-item|cp|xcopy|robocopy)(?=\s)",
        re.IGNORECASE,
    ),
    re.compile(r">{1,2}\s*[\"']?[^\s\"']*data[\\/]+raw", re.IGNORECASE),  # redirect into raw
    re.compile(r"(?:sed|perl)\s+(?:-\w*\s+)*-i", re.IGNORECASE),  # in-place edit
    re.compile(r"attrib\s+(?:\S+\s+)*-r\b", re.IGNORECASE),  # removing read-only
    re.compile(r"""open\([^)]*[\"'][wax]\+?b?[\"']""", re.IGNORECASE),  # open(..., "w")
    re.compile(r"write_(?:text|bytes)\s*\(|\.to_(?:csv|json|parquet)\s*\(", re.IGNORECASE),
]

# ─── 3. secrets ────────────────────────────────────────────────────────
SECRET_PATTERNS = [
    ("a Google/Gemini API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("a Groq API key", re.compile(r"gsk_[A-Za-z0-9]{20,}")),
    ("a Supabase secret key", re.compile(r"sb_secret_[A-Za-z0-9_\-]{16,}")),
    ("a Razorpay LIVE key", re.compile(r"rzp_live_[A-Za-z0-9]{8,}")),
    ("a JWT (e.g. a Supabase service_role key)",
     re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("a Postgres URL with a password",
     re.compile(r"postgres(?:ql)?://[^:\s/@]+:(?![\[<$\{])[^@\s]+@", re.IGNORECASE)),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a value assigned to a secret-named variable",
     # UPPER_CASE name containing SECRET/PASSWORD/... then = or : then a long literal.
     # `X_SECRET = os.getenv("X_SECRET")` passes: the literal run stops at "(".
     re.compile(
         r"\b[A-Z0-9_]*(?:SECRET|PASSWORD|API_KEY|TOKEN|PRIVATE_KEY)[A-Z0-9_]*[\"']?"
         r"\s*[=:]\s*[\"']?[A-Za-z0-9_\-./+=]{16,}"
     )),
    ("a secret-named variable that would be embedded in the app (EXPO_PUBLIC_/NEXT_PUBLIC_ values are readable by anyone)",
     re.compile(r"\b(?:EXPO|NEXT)_PUBLIC_[A-Z0-9_]*(?:SECRET|SERVICE_ROLE|PRIVATE|PASSWORD|DATABASE|GEMINI|GROQ|LLM|PAYMENT_SIM)[A-Z0-9_]*")),
]

# ─── 4. real env files (.env, .env.local, .env.production, ...; never .env.example) ──
ENV_FILE_NAME = re.compile(r"^\.env(?:\.(?:local|development|production|test))*$", re.IGNORECASE)
ENV_IN_COMMAND = re.compile(
    r"(?:^|[\s'\"=/\\(])\.env(?:\.(?:local|development|production|test))*(?=$|[\s'\";|&)<>])",
    re.IGNORECASE,
)

# ─── 6. database commands (ask, not deny) ──────────────────────────────
# Checked on db_view(), so notes that merely mention these words don't prompt.
# Scripts count only when Python runs them (file or -m module form), so reading them doesn't prompt.
PY_RUN = r"(?:python[\w.]*|\bpy(?:\.exe)?(?=\s))[^\n;&|]*"
DB_ASK = [
    ("a migration apply (migrate.py --apply)",
     re.compile(PY_RUN + r"\bmigrate(?:\.py)?\b(?![^\n;&|]*--local\b)[^\n;&|]*--apply\b", re.IGNORECASE)),
    ("load_db.py, which writes seed data", re.compile(PY_RUN + r"\bload_db(?:\.py)?\b", re.IGNORECASE)),
    ("a db_write_ script", re.compile(PY_RUN + r"\bdb_write_\w*", re.IGNORECASE)),
    ("SQL DELETE FROM", re.compile(r"\bdelete\s+from\b", re.IGNORECASE)),
    ("TRUNCATE", re.compile(r"\btruncate\b", re.IGNORECASE)),
    ("SQL DROP", re.compile(r"\bdrop\s+(?:table|schema|database)\b", re.IGNORECASE)),
]

SESSION_REMINDER = (
    "Dawat session control (CLAUDE.md): do not begin any work until Saif types exactly `start`. "
    "On `start`: read memory.md in full, summarise where the project left off, propose next steps, "
    "flag anything Saif must do, then wait for his go-ahead. Do not end until he types exactly `end`. "
    "No git commands of any kind."
)


def norm_path(path: str) -> str:
    return path.replace("\\", "/").lower()


def is_raw_path(path: str) -> bool:
    p = norm_path(path)
    return p.startswith("data/raw/") or "/data/raw/" in p or p.endswith("/data/raw") or p == "data/raw"


def is_env_file(path: str) -> bool:
    return bool(ENV_FILE_NAME.match(os.path.basename(path.replace("\\", "/"))))


def find_secret(text: str) -> str | None:
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return label
    return None


# ─── text that is data, not code ───────────────────────────────────────
# A heredoc fed to cat/tee is text being written to a file, so its body is prose and
# must not trip the git/raw/env rules. The redirect target stays in the command, so
# `cat > data/raw/x <<EOF` is still caught. A heredoc piped onward (`cat <<EOF | bash`)
# or fed to an interpreter (`python - <<EOF`) is code and is kept.
HEREDOC_START = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
DATA_SINKS = {"cat", "tee"}
# Quoted strings are consumed whole, so a ";" or "|" inside quotes doesn't end the segment.
ECHO_SEGMENT = re.compile(
    r"(?:^|[;&|\n])\s*(?:echo|printf|write-output|write-host)\b(?:\"[^\"]*\"|'[^']*'|[^\n;&|\"'])*",
    re.IGNORECASE,
)
QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")


def _strip_data_heredocs(command: str) -> str:
    lines = command.split("\n")
    kept: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        match = HEREDOC_START.search(line)
        if match:
            before = re.split(r"&&|\|\||[;|]", line[: match.start()])[-1].split()
            after = line[match.end():]
            is_data = bool(before) and before[0].lower() in DATA_SINKS and "|" not in after
            delimiter = match.group(2)
            j = i + 1
            while j < len(lines) and lines[j].strip() != delimiter:
                if not is_data:
                    kept.append(lines[j])
                j += 1
            if j < len(lines):
                kept.append(lines[j])  # the closing delimiter line
            i = j + 1
            continue
        i += 1
    return "\n".join(kept)


def _strip_echo_text(command: str) -> str:
    """Blank quoted arguments of echo/printf, except a quoted redirect target (> "path")."""
    def blank_segment(seg: re.Match) -> str:
        text = seg.group(0)
        return QUOTED.sub(lambda q: q.group(0) if text[: q.start()].rstrip().endswith(">") else '""', text)
    return ECHO_SEGMENT.sub(blank_segment, command)


def code_view(command: str) -> str:
    """The command with pure-data text removed; used for the git, raw and env rules."""
    return _strip_echo_text(_strip_data_heredocs(command))


# PowerShell here-strings (@'…'@, @"…"@): the closing marker must start a line.
HERE_STRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.DOTALL)
# Commands whose arguments are text to write or a pattern to search for, never code that
# reaches a database. Only used for the database rule: paths stay visible to the raw rule.
TEXT_COMMANDS = (r"add-content|set-content|out-file|ac|sc|tee-object|"
                 r"select-string|sls|grep|egrep|rg|findstr")
TEXT_SEGMENT = re.compile(
    rf"(?:^|[;&|\n])\s*(?:{TEXT_COMMANDS})\b(?:\"[^\"]*\"|'[^']*'|[^\n;&|\"'])*",
    re.IGNORECASE,
)
SEARCH_COMMAND = re.compile(r"^(\s*[;&|\n]?\s*(?:select-string|sls|grep|egrep|rg|findstr))\b", re.IGNORECASE)
STARTS_TEXT_COMMAND = re.compile(rf"^\s*(?:{TEXT_COMMANDS})\b", re.IGNORECASE)
PIPED_TO_TEXT_COMMAND = re.compile(rf"^\s*\|\s*(?:{TEXT_COMMANDS})\b", re.IGNORECASE)


def _strip_text_here_strings(command: str) -> str:
    """Blank a here-string that is a text cmdlet's argument or piped into one."""
    def blank(m: re.Match) -> str:
        if m.group(1) == '"' and "$(" in m.group(0):  # @"…"@ expands subexpressions: code
            return m.group(0)
        segment_start = re.split(r"[;&|\n]", command[: m.start()])[-1]
        if STARTS_TEXT_COMMAND.match(segment_start) or PIPED_TO_TEXT_COMMAND.match(command[m.end():]):
            return '""'
        return m.group(0)
    return HERE_STRING.sub(blank, command)


def db_view(command: str) -> str:
    """code_view, minus text written by content cmdlets or searched for; used for the database rule."""
    def blank(seg: re.Match) -> str:
        text = seg.group(0)
        if "$(" in text:  # a subexpression runs code even inside text
            return text
        search = SEARCH_COMMAND.match(text)
        if search:  # a search pattern and paths, all of it unquoted or not
            return search.group(1)
        return QUOTED.sub('""', text)

    view = _strip_text_here_strings(code_view(command))
    view = TEXT_SEGMENT.sub(blank, view)
    # A quoted string piped into a text cmdlet ("…" | Add-Content x) is data too.
    return re.sub(rf"(\"[^\"]*\"|'[^']*')(?=\s*\|\s*(?:{TEXT_COMMANDS})\b)", '""', view, flags=re.IGNORECASE)


def needs_ask(command: str) -> str | None:
    view = db_view(command)
    for label, pattern in DB_ASK:
        if pattern.search(view):
            return (f"This command runs {label}. It can change a database, so Saif confirms it first "
                    "(Supabase only gets real migrations and the seed; tests use the local database).")
    return None


def check_shell(command: str) -> str | None:
    code = code_view(command)
    if GIT_COMMAND.search(code) or GIT_VIA_SUBPROCESS.search(code):
        return "git/gh commands are not allowed on this project. Saif handles all git and GitHub himself (CLAUDE.md, Session Control)."
    if RAW_PATH.search(code) and any(p.search(code) for p in RAW_MUTATING):
        return "data/raw/ is read-only (CLAUDE.md, Data rules). Reading is fine; write outputs to data/processed/ instead."
    if ENV_IN_COMMAND.search(code):
        return "Real .env files hold Saif's secrets and must not be read or written by Claude. Code loads them at runtime; use .env.example for structure."
    label = find_secret(command)  # secrets: scan everything, prose included
    if label:
        return f"This command contains what looks like {label}. Secrets belong only in backend/.env or hosting dashboards, never in commands or files."
    return None


def check_file_tool(tool: str, tool_input: dict) -> str | None:
    paths = [tool_input.get(k) for k in ("file_path", "notebook_path", "path") if tool_input.get(k)]

    for path in paths:
        if is_env_file(path):
            return "Real .env files hold Saif's secrets and are off-limits to Claude (read and write). Use .env.example for structure."

    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        for path in paths:
            if is_raw_path(path):
                return "data/raw/ is read-only (CLAUDE.md, Data rules). Write outputs to data/processed/ instead."
        new_text = "\n".join(
            str(tool_input.get(k, ""))
            for k in ("content", "new_string", "new_source")
        )
        for edit in tool_input.get("edits", []) or []:
            new_text += "\n" + str(edit.get("new_string", ""))
        label = find_secret(new_text)
        if label:
            return f"The content contains what looks like {label}. Secrets belong only in backend/.env or hosting dashboards, never in code, docs or logs."
    return None


def decide(kind: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": f"[Dawat guard] {reason}",
        }
    }))


def deny(reason: str) -> None:
    decide("deny", reason)


def main() -> int:
    event = json.load(sys.stdin)

    if event.get("hook_event_name") == "SessionStart":
        print(json.dumps({
            "systemMessage": "Dawat: type `start` to begin the session.",
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": SESSION_REMINDER},
        }))
        return 0

    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}

    if tool in ("Bash", "PowerShell"):
        command = str(tool_input.get("command", ""))
        reason = check_shell(command)
        if not reason:
            ask = needs_ask(command)
            if ask:
                decide("ask", ask)
                return 0
    else:
        reason = check_file_tool(tool, tool_input)

    if reason:
        deny(reason)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # fail closed: a broken guard must not silently allow everything
        deny(f"guard hook crashed ({exc!r}); fix .claude/hooks/guard.py")
        sys.exit(0)
