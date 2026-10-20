"""Tests for guard.py. Run from the project root:
    .venv\\Scripts\\python -m pytest .claude/hooks -q

Fake secrets are assembled at runtime so this file never contains a literal
key (the guard would, correctly, refuse to write it).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).with_name("guard.py")

FAKE = {
    "gemini": "AI" + "za" + "Sy" + "A" * 33,
    "groq": "gs" + "k_" + "a1B2" * 6,
    "supabase": "sb_" + "secret_" + "x9Y8" * 5,
    "jwt": "ey" + "J" + "h" * 20 + ".ey" + "J" + "p" * 20 + "." + "s" * 20,
    "postgres": "postgresql://postgres.abc:" + "hunter2hunter2" + "@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
    "assigned": "RAZORPAY_KEY_" + "SECRET=" + "q" * 24,
}


def run(event: dict) -> dict | None:
    out = subprocess.run(
        [sys.executable, str(GUARD)], input=json.dumps(event), capture_output=True, text=True, check=True
    ).stdout.strip()
    return json.loads(out) if out else None


def decision(tool: str, **tool_input) -> str:
    result = run({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input})
    return result["hookSpecificOutput"]["permissionDecision"] if result else "pass"


# ─── 1. git ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cmd", [
    "git status",
    "git commit -m x",
    "cd backend && git add .",
    "ls; git log",
    "echo hi | git hash-object --stdin",
    "(git init)",
    "gh pr create",
    "/usr/bin/git status",
    "& git push",
    "  git push origin main",
    'python -c "import subprocess; subprocess.run([\'git\', \'push\'])"',
])
def test_git_blocked(cmd):
    assert decision("Bash", command=cmd) == "deny"
    assert decision("PowerShell", command=cmd) == "deny"


@pytest.mark.parametrize("cmd", [
    "cat .gitignore",
    "ls frontend/.gitignore",
    "echo digit",
    "npx create-next-app frontend --disable-git",
    "pip install gitpython-free-lookalike",
])
def test_git_lookalikes_allowed(cmd):
    assert decision("Bash", command=cmd) == "pass"


# ─── 2. data/raw ───────────────────────────────────────────────────────
@pytest.mark.parametrize("tool,path", [
    ("Write", "D:\\DAWAT\\data\\raw\\overpass.json"),
    ("Write", "data/raw/new.json"),
    ("Edit", "D:/DAWAT/data/raw/overpass_2026-09-29.json"),
    ("NotebookEdit", "data/raw/x.ipynb"),
])
def test_raw_file_writes_blocked(tool, path):
    field = "notebook_path" if tool == "NotebookEdit" else "file_path"
    assert decision(tool, **{field: path, "content": "{}"}) == "deny"


@pytest.mark.parametrize("cmd", [
    "rm data/raw/overpass.json",
    "rm -rf data/raw",
    "mv data/raw/a.json data/processed/",
    "echo {} > data/raw/a.json",
    "cat x >> data/raw/a.json",
    "sed -i s/a/b/ data/raw/a.json",
    "Remove-Item data\\raw\\a.json",
    "cp data/processed/x.json data/raw/",
    "attrib -R data\\raw\\a.json",
    "python -c \"open('data/raw/a.json', 'w').write('x')\"",
])
def test_raw_shell_mutations_blocked(cmd):
    assert decision("Bash", command=cmd) == "deny"


@pytest.mark.parametrize("cmd", [
    "cat data/raw/overpass.json | head",
    "ls -la data/raw",
    "python -c \"import json; json.load(open('data/raw/a.json'))\"",
    "python data_pipeline/fetch_osm.py",
    "attrib +R data\\raw\\a.json",
    "rm data/processed/tmp.json",
])
def test_raw_reads_and_other_dirs_allowed(cmd):
    assert decision("Bash", command=cmd) == "pass"


def test_raw_read_tool_allowed():
    assert decision("Read", file_path="D:\\DAWAT\\data\\raw\\overpass.json") == "pass"


# ─── 3. secrets ────────────────────────────────────────────────────────
@pytest.mark.parametrize("kind", sorted(FAKE))
def test_secret_in_write_blocked(kind):
    assert decision("Write", file_path="backend/app/x.py", content=f"KEY = '{FAKE[kind]}'\n") == "deny"


@pytest.mark.parametrize("kind", sorted(FAKE))
def test_secret_in_edit_blocked(kind):
    assert decision("Edit", file_path="docs/notes.md", old_string="a", new_string=FAKE[kind]) == "deny"


def test_secret_in_shell_command_blocked():
    assert decision("Bash", command=f"curl -H 'x-key: {FAKE['groq']}' https://example.com") == "deny"


@pytest.mark.parametrize("content", [
    "GEMINI_API_KEY=\nGROQ_API_KEY=\n",                                        # empty .env.example slots
    'RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")\n',               # reading from env in code
    "postgresql://postgres.abc:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres",
    "NEXT_PUBLIC_API_URL=http://localhost:8000\n",
    "Keys start with rzp_test_ in test mode.",
])
def test_non_secrets_allowed(content):
    assert decision("Write", file_path="backend/.env.example", content=content) == "pass"


# ─── 3b. variables that end up inside the mobile/web app bundle ────────
# EXPO_PUBLIC_* / NEXT_PUBLIC_* values are readable by anyone, so a secret-like NAME is
# always a mistake. Names are assembled at runtime (the guard would refuse this file).
PUBLIC_PREFIXES = ["EXPO_PUB" + "LIC_", "NEXT_PUB" + "LIC_"]
BAD_NAME_WORDS = ["SECRET", "SERVICE_ROLE", "PRIVATE", "PASSWORD", "DATABASE", "GEMINI", "GROQ", "LLM", "PAYMENT_SIM"]


@pytest.mark.parametrize("prefix", PUBLIC_PREFIXES)
@pytest.mark.parametrize("word", BAD_NAME_WORDS)
@pytest.mark.parametrize("value", ["", "x"])
def test_secret_named_public_variable_blocked(prefix, word, value):
    line = f"{prefix}APP_{word}_X={value}\n"
    assert decision("Write", file_path="mobile/.env.example", content=line) == "deny"
    assert decision("Bash", command=f"echo '{line.strip()}' >> notes.txt") == "deny"


def test_secret_looking_public_values_blocked():
    # a long literal on a name containing the words API and KEY, and a Google-key-shaped value under a harmless name
    long_value = "q" * 24
    assert decision("Write", file_path="mobile/app.json",
                    content=PUBLIC_PREFIXES[0] + "API_" + "KEY=" + long_value + "\n") == "deny"
    assert decision("Write", file_path="mobile/app.json",
                    content=PUBLIC_PREFIXES[0] + "MAPS=" + FAKE["gemini"] + "\n") == "deny"
    assert decision("Bash", command="export " + PUBLIC_PREFIXES[0] + "MAPS=" + FAKE["gemini"]) == "deny"


@pytest.mark.parametrize("content", [
    PUBLIC_PREFIXES[0] + "API_URL=http://localhost:8000\n",
    PUBLIC_PREFIXES[0] + "SUPABASE_URL=\n" + PUBLIC_PREFIXES[0] + "SUPABASE_PUBLISHABLE_" + "KEY=\n",
    PUBLIC_PREFIXES[0] + "GOOGLE_WEB_CLIENT_ID=1234567890-abcdefghijklmnop.apps.googleusercontent.com\n",
])
def test_public_variables_with_public_names_allowed(content):
    assert decision("Write", file_path="mobile/.env.example", content=content) == "pass"


def test_public_variable_rule_is_what_blocks_names():
    """Planted bug: with the new pattern removed, the name check must stop firing (so the tests above can fail)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("guard_under_test", GUARD)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    attr = "SECRET" + "_PATTERNS"
    probe = PUBLIC_PREFIXES[0] + "GEMINI_X"
    assert guard.find_secret(probe) is not None
    setattr(guard, attr, getattr(guard, attr)[:-1])
    assert guard.find_secret(probe) is None


# ─── 4. real env files ─────────────────────────────────────────────────
@pytest.mark.parametrize("tool,path", [
    ("Read", "mobile/.env"),
    ("Read", "D:\\DAWAT\\mobile\\.env"),
    ("Read", "mobile/.env.local"),
    ("Write", "mobile/.env"),
    ("Edit", "D:/DAWAT/mobile/.env.production"),
])
def test_mobile_env_files_blocked(tool, path):
    assert decision(tool, file_path=path) == "deny"


def test_mobile_env_example_allowed():
    assert decision("Read", file_path="mobile/.env.example") == "pass"


# ─── 4 (cont). real env files ──────────────────────────────────────────
@pytest.mark.parametrize("tool,path", [
    ("Read", "D:\\DAWAT\\backend\\.env"),
    ("Read", "frontend/.env.local"),
    ("Read", "frontend/.env.production"),
    ("Write", "backend/.env"),
    ("Edit", "D:/DAWAT/frontend/.env.local"),
    ("Grep", "backend/.env"),
])
def test_env_files_blocked(tool, path):
    field = "path" if tool == "Grep" else "file_path"
    assert decision(tool, **{field: path}) == "deny"


@pytest.mark.parametrize("cmd", [
    "cat backend/.env",
    "type backend\\.env",
    "Get-Content frontend/.env.local",
    "cp backend/.env.example backend/.env",
    "python -c \"from dotenv import dotenv_values; print(dotenv_values('.env'))\"",
])
def test_env_shell_access_blocked(cmd):
    assert decision("Bash", command=cmd) == "deny"


@pytest.mark.parametrize("cmd", [
    "cat backend/.env.example",
    "python -c \"import os; print(os.environ.get('X'))\"",
    "node -e \"console.log(process.env.NEXT_PUBLIC_API_URL)\"",
])
def test_env_example_and_environ_allowed(cmd):
    assert decision("Bash", command=cmd) == "pass"


def test_env_example_read_allowed():
    assert decision("Read", file_path="backend/.env.example") == "pass"


# ─── prose vs code (fix for the Session 2 false positive) ──────────────
@pytest.mark.parametrize("cmd", [
    # The exact shape that was wrongly blocked: notes appended via a cat heredoc.
    "cd /d/DAWAT && cat >> learning.md <<'EOF'\n"
    "- Write-once raw data: write to a temp file, then rename, and mark data/raw/ read-only.\n"
    "EOF",
    "cat > docs/notes.md <<EOF\nNever run git status here; never read .env files.\nEOF",
    "tee docs/notes.md <<'EOF'\nrm and mv into data/raw are blocked\nEOF",
    'echo "data/raw is read-only; rm and rename are blocked" >> docs/notes.md',
    "printf '%s\\n' 'never touch data/raw or run git push' > docs/notes.md",
])
def test_prose_about_rules_allowed(cmd):
    assert decision("Bash", command=cmd) == "pass"


@pytest.mark.parametrize("cmd", [
    "cat > data/raw/x.json <<'EOF'\n{}\nEOF",                                 # heredoc INTO raw
    "tee data/raw/x.json <<'EOF'\n{}\nEOF",
    "cat <<'EOF' | bash\nrm data/raw/a.json\nEOF",                            # heredoc piped to a shell = code
    "python - <<'EOF'\nopen('data/raw/a.json', 'w').write('x')\nEOF",         # heredoc fed to an interpreter = code
    "bash <<'EOF'\ngit push\nEOF",
    'echo {} > "data/raw/a.json"',                                            # quoted redirect target
    "echo hi && rm data/raw/a.json",                                          # real command after echo
    'echo "x" && git status',
])
def test_code_disguised_near_prose_still_blocked(cmd):
    assert decision("Bash", command=cmd) == "deny"


def test_secret_inside_prose_still_blocked():
    cmd = f"cat >> docs/notes.md <<'EOF'\nkey: {FAKE['gemini']}\nEOF"
    assert decision("Bash", command=cmd) == "deny"


# ─── 6. database commands ask (only when they really run) ─────────────
@pytest.mark.parametrize("cmd", [
    r".venv\Scripts\python backend\db\migrate.py --apply",
    r"cd backend; ..\.venv\Scripts\python db\migrate.py --apply",
    r'& "D:\DAWAT\.venv\Scripts\python.exe" backend/db/migrate.py --verbose --apply',
    r".venv\Scripts\python data_pipeline\load_db.py",
    r".venv\Scripts\python data_pipeline\load_db.py --local",
    r".venv\Scripts\python -m data_pipeline.load_db",
    r"py -3 data_pipeline/load_db.py",
    r".venv\Scripts\python backend\db\db_write_stale_menu.py",
    """python -c "import psycopg; psycopg.connect(u).execute('TRUNCATE carts')\"""",
    """python -c "c.execute('delete from cart_items')\"""",
    """psql -c 'DROP TABLE orders'""",
    "psql -c 'drop schema public cascade'",
    "python - <<'EOF'\nconn.execute('truncate messages')\nEOF",                     # heredoc into python = code
    "Add-Content notes.md 'x'; .venv\\Scripts\\python data_pipeline\\load_db.py",  # real run after a note
    "Get-Content q.sql | psql -c 'truncate carts'",
    'Add-Content log.md "seeded $(python data_pipeline/load_db.py)"',          # subexpression runs code
    "Set-Content x.md -Value @\"\n$(python backend/db/db_write_x.py)\n\"@",
])
def test_db_commands_ask(cmd):
    assert decision("PowerShell", command=cmd) == "ask"
    assert decision("Bash", command=cmd) == "ask"


@pytest.mark.parametrize("cmd", [
    # Saif's Session 18 case: text appended to DECISIONS.md that mentions the trigger firing on TRUNCATE.
    "Add-Content DECISIONS.md 'The 0010 triggers fire on INSERT, UPDATE, DELETE and TRUNCATE.'",
    'Add-Content -Path learning.md -Value "Ran migrate.py --apply after load_db.py; DROP TABLE is refused."',
    "Set-Content docs/notes.md @'\nmigrate.py --apply, then python data_pipeline/load_db.py\ndelete from carts; truncate\n'@",
    "@'\nRan .venv\\Scripts\\python backend\\db\\migrate.py --apply\n'@ | Add-Content memory.md",
    '"python db_write_x.py ran; truncate refused" | Out-File -Append notes.md',
    "Add-Content notes.md 'a; python load_db.py; b'",                           # separators inside quotes
    "cat >> learning.md <<'EOF'\n.venv\\Scripts\\python backend\\db\\migrate.py --apply\nTRUNCATE\nEOF",
    'echo "never TRUNCATE on Supabase" >> notes.md',
    "grep -rn truncate backend/app",
    "Select-String -Path backend\\db\\migrations\\*.sql -Pattern 'drop table'",
    "rg -n \"delete from\" backend",
    "grep -n conn data_pipeline/load_db.py",                                     # reading the script
    "Get-Content data_pipeline/load_db.py",
    "cat backend/db/db_write_stale_menu.py",
    r".venv\Scripts\python backend\db\migrate.py",                               # plan mode
    r".venv\Scripts\python backend\db\migrate.py --local --apply",               # local rehearsal DB
    r".venv\Scripts\python backend\db\migrate.py --local --test",
    r".venv\Scripts\python -m pytest -q -p no:cacheprovider backend/tests/test_load_db_helpers.py",
])
def test_db_mentions_and_reads_pass(cmd):
    assert decision("PowerShell", command=cmd) == "pass"


def test_deny_beats_ask():
    assert decision("Bash", command="git log; python data_pipeline/load_db.py") == "deny"


# ─── 5. session start ──────────────────────────────────────────────────
def test_session_start_injects_reminder():
    result = run({"hook_event_name": "SessionStart", "source": "startup"})
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "`start`" in context and "memory.md" in context


# ─── robustness ────────────────────────────────────────────────────────
def test_malformed_input_fails_closed():
    out = subprocess.run([sys.executable, str(GUARD)], input="not json", capture_output=True, text=True).stdout
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
