"""Localhost control server for the host process.

Accepts a single client (the Blender add-on) and reads newline-delimited JSON
commands, dispatching each to a handler callback. Runs on a background thread so
the pywebview GUI loop owns the main thread.

Protocol (one JSON object per line):
  {"cmd": "set_mode", "mode": "active|background|off", "opacity": f, "interact": b}
  {"cmd": "set_opacity", "value": f}
  {"cmd": "set_clickthrough", "value": b}
  {"cmd": "set_interact", "value": b}
  {"cmd": "set_bounds", "x": i, "y": i, "w": i, "h": i}
  {"cmd": "set_url", "url": s}
  {"cmd": "back"} | {"cmd": "forward"} | {"cmd": "reload"}
  {"cmd": "hide"}
  {"cmd": "quit"}
"""

import json
import socket
import threading


class ControlServer:
    def __init__(self, port, dispatch):
        self._port = port
        self._dispatch = dispatch
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self):
        self._thread.start()

    def _serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self._port))
        srv.listen(1)
        conn, _ = srv.accept()
        with conn:
            buf = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        command = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    self._dispatch(command)
