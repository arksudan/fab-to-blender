"""Win32 window manipulation for the overlay, via ctypes.

All of these act on an HWND. The host finds its own window's HWND by unique
title (see host.py) and passes it here.

Capabilities:
  * always-on-top toggle           -> SetWindowPos(HWND_TOPMOST/NOTOPMOST)
  * per-window opacity             -> WS_EX_LAYERED + SetLayeredWindowAttributes
  * click-through (input passthru) -> WS_EX_TRANSPARENT
  * bounds                         -> SetWindowPos move/size
  * arrow/space key forwarding     -> WH_KEYBOARD_LL hook + PostMessage
"""

import ctypes
import ctypes.wintypes as wt
import threading

user32 = ctypes.windll.user32

# Extended window styles
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

# SetWindowPos
HWND_TOPMOST = wt.HWND(-1)
HWND_NOTOPMOST = wt.HWND(-2)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

# SetLayeredWindowAttributes
LWA_ALPHA = 0x00000002

# Hook / messages
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
HC_ACTION = 0

# Virtual key codes we care about (YouTube controls).
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
_FORWARDED_KEYS = {VK_SPACE, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN}


def _set_exstyle_bit(hwnd, bit, on):
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style = (style | bit) if on else (style & ~bit)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    return style


def activate(hwnd):
    """Bring to foreground and give keyboard focus (needed for typing)."""
    user32.SetForegroundWindow(hwnd)
    user32.SetActiveWindow(hwnd)
    # Keyboard focus belongs to WebView2's Chromium child, not its outer frame.
    user32.SetFocus(find_web_content_hwnd(hwnd))


def set_topmost(hwnd, on):
    user32.SetWindowPos(
        hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
        0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def set_opacity(hwnd, factor):
    """factor in [0, 1]. Requires the layered style, which we keep on always."""
    _set_exstyle_bit(hwnd, WS_EX_LAYERED, True)
    alpha = max(0, min(255, int(round(factor * 255))))
    user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)


def set_clickthrough(hwnd, on):
    # Layered must stay set for opacity; only toggle the transparent bit.
    _set_exstyle_bit(hwnd, WS_EX_LAYERED, True)
    _set_exstyle_bit(hwnd, WS_EX_TRANSPARENT, on)


def set_bounds(hwnd, x, y, w, h):
    user32.SetWindowPos(
        hwnd, None, int(x), int(y), int(w), int(h),
        SWP_NOACTIVATE | SWP_SHOWWINDOW,
    )


def find_web_content_hwnd(parent_hwnd):
    """Find the Chromium/WebView2 child HWND that should receive key events."""
    target = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _enum(hwnd, _lparam):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        # WebView2 hosts content in a "Chrome_WidgetWin_*" / "Chrome_RenderWidget".
        if "Chrome" in buf.value or "WebView2" in buf.value:
            target.append(hwnd)
            return False
        return True

    user32.EnumChildWindows(parent_hwnd, _enum, 0)
    return target[0] if target else parent_hwnd


# --- low-level keyboard hook ----------------------------------------------
# Runs its own thread with a message pump (required for WH_KEYBOARD_LL).

class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wt.ULONG)),
    ]


_HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wt.WPARAM, wt.LPARAM
)


class KeyForwarder:
    """When `enabled`, swallows arrow/space globally and posts them to the
    web content window so YouTube responds without the overlay taking focus."""

    def __init__(self):
        self.enabled = False
        self.target_hwnd = None
        self._hook = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        # Keep a reference so the callback is not garbage collected.
        self._proc = _HOOKPROC(self._callback)
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, None, 0
        )
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _callback(self, nCode, wParam, lParam):
        if nCode == HC_ACTION and self.enabled and self.target_hwnd:
            kb = ctypes.cast(lParam,
                             ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if kb.vkCode in _FORWARDED_KEYS:
                msg = WM_KEYDOWN if wParam in (WM_KEYDOWN, 0x0104) else WM_KEYUP
                user32.PostMessageW(self.target_hwnd, msg, kb.vkCode, 0)
                return 1  # swallow so Blender does not also act on it
        return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)
