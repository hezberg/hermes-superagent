"""Config edits apply themselves.

superagent.yaml is the operator's file; the profiles Hermes runs
are renders of it. Demanding a manual installer run after every
edit is a ritual, not a mechanism (operator's verdict, 2026-11-01:
"I edit the file, then I still have to run upgrade?"). So the
suite reconciles on its own: whenever the config is newer than the
install state, the next CLI command — or the reminder tick, within
one cycle — re-runs the installer from the managed source checkout.

Failures (a config that does not validate) are surfaced once per
config version, never spammed every tick; the bookkeeping lives in
reconcile.json next to the state.
"""
import json
import os
import subprocess
import sys


def _book_path(suite_dir):
    return os.path.join(suite_dir, "reconcile.json")


def _read_book(suite_dir):
    try:
        with open(_book_path(suite_dir), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_book(suite_dir, book):
    try:
        with open(_book_path(suite_dir), "w", encoding="utf-8") as fh:
            json.dump(book, fh)
    except OSError:
        pass


def config_stale(suite_dir):
    cfg = os.path.join(suite_dir, "superagent.yaml")
    state = os.path.join(suite_dir, "state.json")
    if not os.path.isfile(cfg) or not os.path.isfile(state):
        return False
    return os.path.getmtime(cfg) > os.path.getmtime(state)


def _default_runner(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def maybe_reconcile(home, suite_dir, interactive=False, runner=None):
    """Reconcile if the config outruns the install state.

    Returns {"status": ..., "message": ...}: status is one of
    "fresh" (nothing to do), "reconciled", "failed", "skipped"
    (no source checkout to run the installer from). `message` is
    set only when the caller should surface it: a fresh failure, or
    any attempt a human is watching (interactive=True).
    """
    if not config_stale(suite_dir):
        return {"status": "fresh", "message": None}
    cfg_path = os.path.join(suite_dir, "superagent.yaml")
    mtime = os.path.getmtime(cfg_path)
    book = _read_book(suite_dir)
    if book.get("config_mtime") == mtime and book.get("failed") and not interactive:
        return {"status": "failed", "message": None}

    from .upgrade import pick_source, read_state

    _mode, source = pick_source(read_state(suite_dir), suite_dir)
    installer = os.path.join(source, "scripts", "install.py")
    if not os.path.isfile(installer):
        return {"status": "skipped", "message": None}
    if runner is None:
        runner = _default_runner
    code, output = runner([sys.executable, installer, "--home", home])
    if code == 0:
        _write_book(suite_dir, {"config_mtime": mtime, "failed": False})
        return {"status": "reconciled", "message": None}
    error_lines = [ln.strip() for ln in output.splitlines() if "ERROR" in ln]
    error = error_lines[0] if error_lines else "installer exited with an error"
    _write_book(suite_dir, {"config_mtime": mtime, "failed": True, "error": error})
    return {
        "status": "failed",
        "message": f"superagent config update was NOT applied: {error} "
                   "(details: hermes superagent doctor)",
    }


def set_role_model(suite_dir, profile, model):
    """Set one role's model in superagent.yaml, as a text edit.

    A parse-and-redump would destroy the file's comments and the
    operator's formatting, so this finds the role by its `profile:`
    line and rewrites (or inserts) the `model:` line inside that
    block only. Empty model means "inherit". Returns True when the
    profile was found.
    """
    path = os.path.join(suite_dir, "superagent.yaml")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    target = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("profile:"):
            value = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            if value == profile:
                target = i
                break
    if target is None:
        return False
    indent = len(lines[target]) - len(lines[target].lstrip(" "))
    pad = " " * indent
    new_line = f'{pad}model: "{model}"'
    for j in range(target + 1, len(lines)):
        line = lines[j]
        if not line.strip() or line.strip().startswith("#"):
            continue
        ind = len(line) - len(line.lstrip(" "))
        if ind < indent or (ind == indent and line.strip().startswith("- ")):
            break
        if ind == indent and line.strip().startswith("model:"):
            lines[j] = new_line
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            return True
        if ind < indent:
            break
    lines.insert(target + 1, new_line)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return True
