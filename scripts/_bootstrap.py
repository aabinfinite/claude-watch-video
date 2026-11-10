"""Give the pipeline a working Python environment on any machine.

When the interpreter running watch_video.py lacks the core packages, build a
private virtualenv at ~/.watch-video/venv and re-exec the same command inside
it. Nothing is installed into the user's own Python.

The interpreter for that venv must be one the pinned packages have wheels
for (PyAV, used by faster-whisper, lags new Python releases by months). We
take the first python3.14 .. python3.10 on PATH; failing that, `uv` (on PATH,
or installed into ~/.watch-video/tools) creates the venv and downloads a
managed CPython for it.

Opt out with WATCH_VIDEO_NO_BOOTSTRAP=1.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from _common import ExitCode, die, emit

HOME_DIR = Path.home() / ".watch-video"
VENV_DIR = HOME_DIR / "venv"
TOOLS_DIR = HOME_DIR / "tools"
# Touched after each successful install / yt-dlp refresh.
STAMP = VENV_DIR / ".watch-video-deps"
# Site extractors in yt-dlp break often (Instagram, TikTok, X); refresh it
# when the copy in our venv is older than this.
YTDLP_MAX_AGE_SECONDS = 7 * 24 * 3600
SUPPORTED_MINORS = range(14, 9, -1)   # 3.14 .. 3.10, newest first
UV_PYTHON = "3.12"

# Import name -> pip requirement. Mirrors mcp-server/pyproject.toml [full],
# minus the hosted-API SDKs that only optional steps use.
REQUIREMENTS = {
    "yt_dlp": "yt-dlp",
    "faster_whisper": "faster-whisper>=1.0.0",
    "av": "av<19",  # faster-whisper 1.2 passes metadata_errors=, dropped in av 19
    "PIL": "Pillow>=10.0",
    "imagehash": "imagehash>=4.3.0",
    "docx": "python-docx>=1.0.0",
}
CORE_MODULES = ("yt_dlp", "faster_whisper")


def _venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _missing(modules) -> list[str]:
    return [m for m in modules if importlib.util.find_spec(m) is None]


def _run(cmd: list[str], fatal: bool = True) -> bool:
    emit("progress", step="bootstrap", cmd=" ".join(str(c) for c in cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True)
    if r.returncode == 0:
        return True
    if fatal:
        die(ExitCode.MISSING_DEP,
            f"setting up {VENV_DIR} failed running {cmd[0]}: "
            f"{r.stdout.strip()[-800:]}",
            dependency="python-env")
    return False


def _find_python() -> str | None:
    """A python3.10-3.14 interpreter, or None."""
    candidates = []
    if (3, 10) <= sys.version_info[:2] <= (3, 14):
        candidates.append(sys.executable)
    candidates += [shutil.which(f"python3.{m}") for m in SUPPORTED_MINORS]
    if os.name == "nt" and shutil.which("py"):
        for m in SUPPORTED_MINORS:
            r = subprocess.run(["py", f"-3.{m}", "-c",
                                "import sys; print(sys.executable)"],
                               capture_output=True, text=True)
            if r.returncode == 0:
                candidates.append(r.stdout.strip())
    return next((c for c in candidates if c), None)


def _existing_uv() -> str | None:
    tool_uv = _venv_python(TOOLS_DIR).parent / ("uv.exe" if os.name == "nt" else "uv")
    return shutil.which("uv") or (str(tool_uv) if tool_uv.exists() else None)


def _find_uv() -> str | None:
    if _existing_uv():
        return _existing_uv()
    # uv ships as a py3-none wheel, so any Python can pip-install it.
    emit("progress", step="bootstrap",
         msg=f"no Python 3.10-3.14 found; installing uv into {TOOLS_DIR}")
    _run([sys.executable, "-m", "venv", str(TOOLS_DIR)])
    _run([str(_venv_python(TOOLS_DIR)), "-m", "pip", "install", "-q", "uv"])
    return _existing_uv()


def _create_venv() -> None:
    python = _find_python()
    if python:
        emit("progress", step="bootstrap", msg=f"creating {VENV_DIR} with {python}")
        _run([python, "-m", "venv", str(VENV_DIR)])
        return
    uv = _find_uv()
    if not uv:
        die(ExitCode.MISSING_DEP,
            "No Python 3.10-3.14 found and uv could not be installed. Install "
            "Python 3.12 (python.org or your package manager) and re-run.",
            dependency="python")
    emit("progress", step="bootstrap",
         msg=f"creating {VENV_DIR} with a uv-managed Python {UV_PYTHON}")
    _run([uv, "venv", "--python", UV_PYTHON, str(VENV_DIR)])


def _pip_install(packages: list[str], upgrade: bool = False,
                 fatal: bool = True) -> bool:
    py = str(_venv_python(VENV_DIR))
    flags = ["-q"] + (["-U"] if upgrade else [])
    has_pip = subprocess.run([py, "-m", "pip", "--version"],
                             capture_output=True).returncode == 0
    if has_pip:
        return _run([py, "-m", "pip", "install", *flags, *packages], fatal)
    uv = _existing_uv()  # uv-created venvs have no pip
    if not uv:
        if not fatal:
            return False
        die(ExitCode.MISSING_DEP, f"{VENV_DIR} has no pip and uv is gone; "
            "delete that folder and re-run.", dependency="python-env")
    return _run([uv, "pip", "install", "--python", py, *flags, *packages], fatal)


def _refresh_ytdlp() -> None:
    try:
        age = time.time() - STAMP.stat().st_mtime
    except OSError:
        age = float("inf")
    if age < YTDLP_MAX_AGE_SECONDS:
        return
    # A failed refresh must not stop a run the old copy may handle fine.
    if _pip_install(["yt-dlp"], upgrade=True, fatal=False):
        STAMP.touch()
    else:
        emit("warning", step="bootstrap",
             msg="could not update yt-dlp; using the installed copy")


def ensure_environment() -> None:
    """Re-exec inside the private venv when this interpreter can't run the
    pipeline. Returns normally when nothing needs doing."""
    if os.environ.get("WATCH_VIDEO_NO_BOOTSTRAP"):
        return
    in_venv = Path(sys.prefix).resolve() == VENV_DIR.resolve()
    if in_venv:
        _refresh_ytdlp()
        return
    if not _missing(CORE_MODULES):
        return
    if os.environ.get("WATCH_VIDEO_BOOTSTRAPPED"):
        # We already re-exec'd once and the venv still lacks them.
        die(ExitCode.MISSING_DEP,
            f"{VENV_DIR} is missing {', '.join(_missing(CORE_MODULES))} even "
            "after setup. Delete that folder and re-run.",
            dependency="python-env")

    t0 = time.time()
    emit("start", step="bootstrap",
         msg=f"{sys.executable} lacks {', '.join(_missing(CORE_MODULES))}; "
             f"using a private environment at {VENV_DIR}")
    py = _venv_python(VENV_DIR)
    if not py.exists():
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        _create_venv()
    probe = subprocess.run(
        [str(py), "-c",
         "import importlib.util, sys; "
         f"print(' '.join(m for m in {list(REQUIREMENTS)!r} "
         "if importlib.util.find_spec(m) is None))"],
        capture_output=True, text=True)
    absent = probe.stdout.split() if probe.returncode == 0 else list(REQUIREMENTS)
    if absent:
        _pip_install([REQUIREMENTS[m] for m in absent])
        STAMP.touch()
    emit("complete", step="bootstrap", duration_seconds=round(time.time() - t0, 2),
         python=str(py))

    env = {**os.environ, "WATCH_VIDEO_BOOTSTRAPPED": "1"}
    argv = [str(py), *sys.argv]
    if os.name == "nt":
        # os.execv on Windows spawns a detached child and returns control to
        # the caller's shell early; run it and pass its exit code through.
        sys.exit(subprocess.call(argv, env=env))
    os.execve(str(py), argv, env)
