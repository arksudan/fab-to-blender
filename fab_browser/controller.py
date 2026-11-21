"""Owns the webview host subprocess and the IPC link to it.

The Blender side is a *client*: it spawns `webview_host/host.py` (using Blender's
own Python interpreter so the dependency install location is shared) and sends
newline-delimited JSON commands over a localhost TCP socket. The host renders
the actual WebView2 window and applies all win32 window tricks.

All functions here are safe to call when nothing is running — they degrade to
no-ops so the property update callbacks stay simple.
"""

import json
import os
import socket
import subprocess
import sys
import threading

# Module-level singletons. There is only ever one overlay window.
_proc = None            # subprocess.Popen of the host
_sock = None            # connected control socket
_lock = threading.Lock()
_port = 0

# Loopback only; the protocol is unauthenticated so it must not be exposed.
_HOST = "127.0.0.1"


def _host_script():
    # webview_host ships inside the package so it travels with the add-on when
    # zipped/installed. It is launched as a standalone script (by file path, not
    # import), so its own directory is on sys.path for `import winapi` / `import ipc`.
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "webview_host", "host.py")


def _pick_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((_HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def is_running():
    return _proc is not None and _proc.poll() is None


def ensure_running(url):
    """Start the host process if it is not already alive, then connect."""
    global _proc, _sock, _port
    with _lock:
        if is_running() and _sock is not None:
            return

        _port = _pick_port()
        script = _host_script()
        if not os.path.exists(script):
            raise RuntimeError(f"webview host script not found: {script}")

        # sys.executable is Blender's bundled python.exe; using it means
        # pywebview installed for Blender is visible to the host too.
        _proc = subprocess.Popen(
            [sys.executable, script,
             "--port", str(_port),
             "--url", url],
            cwd=os.path.dirname(script),
        )
        _connect()


def _connect(timeout=10.0):
    """Connect to the host's control server, retrying until it binds."""
    global _sock
    import time
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            s = socket.create_connection((_HOST, _port), timeout=1.0)
            _sock = s
            return
        except OSError as err:
            last_err = err
            time.sleep(0.1)
    raise RuntimeError(f"could not reach webview host on {_port}: {last_err}")


def send(**command):
    """Send one JSON command; silently drops if the host is gone."""
    global _sock
    if _sock is None or not is_running():
        return
    payload = (json.dumps(command) + "\n").encode("utf-8")
    try:
        with _lock:
            _sock.sendall(payload)
    except OSError:
        # Host died underneath us; reset so a later ensure_running() respawns.
        _reset()


def shutdown():
    """Tell the host to quit and tear everything down. Called on unregister."""
    global _proc, _sock
    if _sock is not None and is_running():
        try:
            _sock.sendall((json.dumps({"cmd": "quit"}) + "\n").encode())
        except OSError:
            pass
    if _proc is not None:
        try:
            _proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _reset()


def _reset():
    global _proc, _sock
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
    _sock = None
    _proc = None


def register():
    pass


def unregister():
    shutdown()
