"""Webview host process entry point.

Launched by the Blender add-on's controller as:
    python host.py --port <p> --url <u>

Creates a resizable pywebview/WebView2 window, then applies mode/opacity/
clickthrough/bounds in response to control commands received over the socket.
pywebview must own the main thread, so the GUI starts last and the control
server + key forwarder run on background threads.

A self-contained mini-Chrome toolbar (back / forward / reload / address bar) is
injected into every page on load; all of its actions run in-page JS, so it does
not depend on a Python<->JS bridge surviving a site's CSP.
"""

import argparse
import sys

import webview  # pip install pywebview pythonnet

import winapi
from ipc import ControlServer

# A unique title lets us locate our own HWND via FindWindowW once the GUI is up.
_WINDOW_TITLE = "BlenderWebviewOverlay"

_window = None
_hwnd = None
_forwarder = winapi.KeyForwarder()
_mode = "off"

# Injected on every page load. Builds a fixed top bar, self-heals on SPA
# navigations (interval re-runs build()), and keeps the address field in sync.
_TOOLBAR_HEIGHT = 40
_TOOLBAR_JS = r"""
(function () {
  var ID = '__bw_toolbar__';
  function mkbtn(label, fn) {
    var b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = 'flex:0 0 auto;width:30px;height:26px;border:none;' +
      'border-radius:4px;background:#3c4043;color:#e8eaed;font-size:14px;' +
      'cursor:pointer;line-height:26px;padding:0;';
    b.addEventListener('click', fn);
    return b;
  }
  function navigate(v) {
    v = (v || '').trim();
    if (!v) return;
    if (!/^[a-z]+:\/\//i.test(v)) {
      if (/^[^\s.]+(\.[^\s.]+)+(\/.*)?$/.test(v)) v = 'https://' + v;
      else v = 'https://www.fab.com/search?q=' + encodeURIComponent(v);
    }
    location.href = v;
  }
  function build() {
    if (document.getElementById(ID)) return;
    var bar = document.createElement('div');
    bar.id = ID;
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:__H__px;' +
      'z-index:2147483647;display:flex;align-items:center;gap:6px;' +
      'padding:0 8px;background:#202124;border-bottom:1px solid #000;' +
      'box-sizing:border-box;font-family:Segoe UI,Arial,sans-serif;';
    bar.appendChild(mkbtn('◀', function () { history.back(); }));
    bar.appendChild(mkbtn('▶', function () { history.forward(); }));
    bar.appendChild(mkbtn('⟳', function () { location.reload(); }));
    var url = document.createElement('input');
    url.id = ID + '_url';
    url.type = 'text';
    url.spellcheck = false;
    url.value = location.href;
    url.style.cssText = 'flex:1 1 auto;height:26px;border:none;' +
      'border-radius:13px;padding:0 12px;background:#5f6368;color:#fff;' +
      'font-size:13px;outline:none;min-width:0;';
    url.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); navigate(url.value); }
    });
    url.addEventListener('focus', function () { url.select(); });
    bar.appendChild(url);
    document.documentElement.appendChild(bar);
    if (document.body) {
      document.body.style.setProperty('margin-top', '__H__px', 'important');
    }
  }
  function sync() {
    var u = document.getElementById(ID + '_url');
    if (u && document.activeElement !== u) u.value = location.href;
  }
  build();
  setInterval(function () { build(); sync(); }, 800);
  ['pushState', 'replaceState'].forEach(function (m) {
    var orig = history[m];
    history[m] = function () {
      var r = orig.apply(this, arguments);
      setTimeout(sync, 0);
      return r;
    };
  });
  window.addEventListener('popstate', function () { setTimeout(sync, 0); });
})();
""".replace("__H__", str(_TOOLBAR_HEIGHT))


def _resolve_hwnd():
    global _hwnd
    if _hwnd:
        return _hwnd
    _hwnd = winapi.user32.FindWindowW(None, _WINDOW_TITLE)
    if _hwnd:
        _forwarder.target_hwnd = winapi.find_web_content_hwnd(_hwnd)
    return _hwnd


def _apply_mode(mode, opacity=None, interact=None):
    """Translate a mode into the concrete window-style combination."""
    global _mode
    _mode = mode
    hwnd = _resolve_hwnd()
    if not hwnd:
        return

    if mode == "off":
        winapi.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        _forwarder.enabled = False
        return

    winapi.user32.ShowWindow(hwnd, 5)      # SW_SHOW
    winapi.set_topmost(hwnd, True)

    if mode == "active":
        winapi.set_clickthrough(hwnd, False)
        winapi.set_opacity(hwnd, 1.0)
        winapi.activate(hwnd)      # take focus so text fields receive typing
        _forwarder.enabled = False
    elif mode == "background":
        winapi.set_clickthrough(hwnd, True)
        if opacity is not None:
            winapi.set_opacity(hwnd, opacity)
        _forwarder.enabled = bool(interact)


def _dispatch(command):
    """Handle one control command. Runs on the IPC thread."""
    cmd = command.get("cmd")
    hwnd = _resolve_hwnd()

    if cmd == "set_mode":
        _apply_mode(command.get("mode", "off"),
                    command.get("opacity"),
                    command.get("interact"))
    elif cmd == "set_opacity" and hwnd:
        winapi.set_opacity(hwnd, command.get("value", 1.0))
    elif cmd == "set_clickthrough" and hwnd:
        winapi.set_clickthrough(hwnd, bool(command.get("value")))
    elif cmd == "set_interact":
        _forwarder.enabled = bool(command.get("value")) and _mode == "background"
    elif cmd == "set_bounds" and hwnd:
        winapi.set_bounds(hwnd, command["x"], command["y"],
                          command["w"], command["h"])
    elif cmd == "set_url" and _window is not None:
        _window.load_url(command.get("url", "about:blank"))
    elif cmd == "back" and _window is not None:
        # history.back/forward work cross-origin (JS can call them on any page).
        _window.evaluate_js("history.back()")
    elif cmd == "forward" and _window is not None:
        _window.evaluate_js("history.forward()")
    elif cmd == "reload" and _window is not None:
        _window.evaluate_js("location.reload()")
    elif cmd == "hide" and hwnd:
        winapi.user32.ShowWindow(hwnd, 0)
    elif cmd == "quit":
        if _window is not None:
            _window.destroy()


def _inject_toolbar(*_args):
    """Re-inject the mini-Chrome toolbar after each full page load."""
    if _window is not None:
        try:
            _window.evaluate_js(_TOOLBAR_JS)
        except Exception:
            pass


def _on_started():
    """Runs after the GUI is up (pywebview calls this on a worker thread)."""
    _resolve_hwnd()
    _forwarder.start()


def main():
    global _window
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--url", default="https://www.youtube.com")
    args = parser.parse_args()

    server = ControlServer(args.port, _dispatch)
    server.start()

    _window = webview.create_window(
        _WINDOW_TITLE,
        args.url,
        # A real frame gives OS resize borders + a drag bar, and — crucially —
        # NOT easy_drag means clicks land in the page so text fields can focus
        # and receive typing. easy_drag turned every click into a window-drag,
        # which is why typing did nothing.
        frameless=False,
        resizable=True,
        on_top=True,
        width=720,
        height=460,
        min_size=(320, 240),
    )
    # Inject the toolbar on first load and on every subsequent navigation.
    _window.events.loaded += _inject_toolbar
    # gui='edgechromium' forces WebView2 (needed for YouTube). Falls back if absent.
    webview.start(_on_started, gui="edgechromium")


if __name__ == "__main__":
    sys.exit(main())
