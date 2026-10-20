"""Start, stop or check the LOCAL development API server (uvicorn), for Claude Code and for Saif.

    ..\\.venv\\Scripts\\python dev_server.py start [--port 8000]   (from backend/)  LOCAL mode, the default
    ..\\.venv\\Scripts\\python dev_server.py start --supabase         the Supabase database (light checks only)
    ..\\.venv\\Scripts\\python dev_server.py status
    ..\\.venv\\Scripts\\python dev_server.py stop

LOCAL mode (D-059; Saif, Session 20: daily work avoids Supabase): the server uses the local dev database dawat_dev
(built by db/local_setup.py --dev) and the local dev login (app/devauth.py), so nothing reaches Supabase. Both are set
as environment variables of the server process only; nothing is written to backend/.env. --supabase starts it on
backend/.env's DATABASE_URL with Supabase sign-in, and makes sure the dev login flag is NOT passed on.

`stop` only ever stops the one process that `start` launched: its PID is recorded in .dev_server.pid,
and before stopping it checks that the PID still belongs to a Python process (PIDs get reused).
It never touches any other process. This is why .claude/settings.json can allow this script without a
prompt while blanket process-killing commands stay unallowed.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PID_FILE = HERE / ".dev_server.pid"
LOG_FILE = HERE / ".dev_server.log"


def _read_state() -> dict | None:
    try:
        return json.loads(PID_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def _is_our_python(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        return f'"{pid}"' in out and "python" in out.lower()
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    cmdline = Path(f"/proc/{pid}/cmdline")
    return not cmdline.exists() or b"uvicorn" in cmdline.read_bytes()


def _healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def _server_env(supabase: bool) -> dict:
    env = dict(os.environ)
    env.pop("DAWAT_DEV_LOGIN", None)
    if not supabase:
        sys.path.insert(0, str(HERE))
        from app.localdb import dev_dsn          # exits with a clear message if the local database isn't set up
        env["DATABASE_URL"] = dev_dsn()          # wins over backend/.env (load_dotenv never overrides)
        env["DAWAT_DEV_LOGIN"] = "1"
    return env


def start(port: int, supabase: bool = False) -> int:
    state = _read_state()
    if state and _is_our_python(state["pid"]):
        print(f"Already running: PID {state['pid']} on port {state['port']} ({state.get('mode', 'supabase')} mode).")
        return 0
    mode = "supabase" if supabase else "local"
    env = _server_env(supabase)
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0
    with LOG_FILE.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=HERE,
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags,
                                start_new_session=os.name != "nt", env=env)
    PID_FILE.write_text(json.dumps({"pid": proc.pid, "port": port, "mode": mode}), encoding="utf-8")
    for _ in range(30):
        if _healthy(port):
            where = "local dawat_dev + dev login" if mode == "local" else "SUPABASE database + Supabase sign-in"
            print(f"Started: PID {proc.pid}, http://127.0.0.1:{port}, {where} (log: {LOG_FILE.name}).")
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    print(f"Server did not become healthy. Last log lines:\n{LOG_FILE.read_text(encoding='utf-8')[-1500:]}")
    return 1


def stop() -> int:
    state = _read_state()
    if not state:
        print("Not running (no .dev_server.pid).")
        return 0
    pid = state["pid"]
    if _is_our_python(pid):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"Stopped PID {pid}.")
    else:
        print(f"PID {pid} is no longer our server; nothing stopped.")
    PID_FILE.unlink(missing_ok=True)
    return 0


def status() -> int:
    state = _read_state()
    if state and _is_our_python(state["pid"]):
        print(f"Running: PID {state['pid']}, port {state['port']}, {state.get('mode', 'supabase')} mode, "
              f"healthy: {_healthy(state['port'])}.")
    else:
        print("Not running.")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["start", "stop", "status"])
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--supabase", action="store_true", help="start on the Supabase database (default: local dawat_dev)")
    a = ap.parse_args()
    sys.exit(start(a.port, a.supabase) if a.action == "start" else stop() if a.action == "stop" else status())
