#!/usr/bin/env python3
"""One-click launcher for barloni-gram-seva.

Usage:
    python start.py                 # set up (if needed) and run the app
    python start.py --setup-only    # only install/prepare, do not start server
    python start.py --no-browser    # start without auto-opening the browser

On the FIRST run this will, only if needed:
  1. Create a .env file (with a secure random SECRET_KEY) from .env.example
  2. Create an isolated virtual environment in .venv/
  3. Install the Python dependencies from requirements.txt
  4. Start the web server and open it in your browser

On later runs the setup steps are skipped, so it starts quickly.
Python 3.10+ is the only prerequisite.
"""
import hashlib
import os
import secrets
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQ_FILE = ROOT / "requirements.txt"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
REQ_HASH_FILE = VENV_DIR / ".req-hash"

PY_MIN = (3, 10)


def info(msg):
    print(f"\n>>> {msg}")


def warn(msg):
    print(f"\n!!! {msg}")


def check_python_version():
    if sys.version_info < PY_MIN:
        warn(
            f"Python {PY_MIN[0]}.{PY_MIN[1]}+ is required. "
            f"You are running {sys.version.split()[0]}."
        )
        print("    Download a newer Python from https://www.python.org/downloads/")
        sys.exit(1)


def ensure_env_file():
    """Create .env from .env.example with a fresh secret key, if missing."""
    if ENV_FILE.exists():
        return
    if not ENV_EXAMPLE.exists():
        warn(".env.example not found; cannot create .env automatically.")
        return
    info("First-time setup: creating your .env configuration file")
    out = []
    for line in ENV_EXAMPLE.read_text().splitlines():
        if line.startswith("SECRET_KEY="):
            out.append("SECRET_KEY=" + secrets.token_urlsafe(48))
        else:
            out.append(line)
    ENV_FILE.write_text("\n".join(out) + "\n")
    print("    Created .env with a secure random SECRET_KEY.")
    print("    >> Edit .env to set your admin password before going live. <<")


def read_env(key, default):
    """Minimal .env reader (no third-party deps required)."""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(key, default)


def venv_python():
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def has_pip(python_exe):
    return subprocess.run(
        [str(python_exe), "-m", "pip", "--version"],
        capture_output=True,
    ).returncode == 0


def ensure_environment():
    """Return (python_executable, in_venv). Falls back gracefully."""
    py = venv_python()
    if py.exists():
        return str(py), True

    info("Setting up an isolated environment (.venv) — one time only")
    try:
        venv.create(VENV_DIR, with_pip=True)
        return str(venv_python()), True
    except Exception as exc:
        warn("Could not create a virtual environment.")
        print(f"    Reason: {exc}")
        if os.name != "nt":
            print("    Tip (Debian/Ubuntu): sudo apt install python3-venv")
        if has_pip(sys.executable):
            print("    Falling back to a user-level install instead.\n")
            return sys.executable, False
        warn(
            "pip is also unavailable for this Python. Please install "
            "Python 3.10+ (with pip) from https://www.python.org/downloads/"
        )
        sys.exit(1)


def requirements_hash():
    return hashlib.sha256(REQ_FILE.read_bytes()).hexdigest()


def install_deps(python_exe, in_venv):
    """Install dependencies, skipping if already done for this requirements.txt."""
    current = requirements_hash()
    if (
        in_venv
        and REQ_HASH_FILE.exists()
        and REQ_HASH_FILE.read_text().strip() == current
    ):
        return  # already up to date

    info("Installing dependencies (this may take a minute the first time)")
    subprocess.check_call(
        [str(python_exe), "-m", "pip", "install", "--upgrade", "pip"],
        stdout=subprocess.DEVNULL,
    )
    cmd = [str(python_exe), "-m", "pip", "install", "-r", str(REQ_FILE)]
    if not in_venv:
        cmd.insert(4, "--user")
    subprocess.check_call(cmd)
    if in_venv:
        REQ_HASH_FILE.write_text(current)


def open_browser_later(url):
    def _open():
        time.sleep(2.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main():
    os.chdir(ROOT)
    args = set(sys.argv[1:])

    check_python_version()
    ensure_env_file()
    python_exe, in_venv = ensure_environment()
    install_deps(python_exe, in_venv)

    if "--setup-only" in args:
        info("Setup complete. Run 'python start.py' to start the app.")
        return

    host = read_env("HOST", "127.0.0.1")
    port = read_env("PORT", "8000")
    village = read_env("VILLAGE_NAME", "Barloni")
    browse_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{browse_host}:{port}"

    info(f"Starting {village} Gram Seva")
    print(f"    Open in your browser: {url}")
    print("    Press Ctrl+C to stop the server.")

    if "--no-browser" not in args:
        open_browser_later(url)

    cmd = [
        str(python_exe), "-m", "uvicorn", "app.main:app",
        "--host", host, "--port", str(port),
    ]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        info("Server stopped. Goodbye!")


if __name__ == "__main__":
    main()
