"""Track the 3D viewport's on-screen rectangle and push it to the host.

In background mode the overlay must sit exactly over the 3D viewport region.
Blender gives us region coordinates relative to its own window (origin
bottom-left); we map those to absolute desktop pixels via the Win32 client rect
of Blender's GHOST window, then send `set_bounds` whenever the rectangle moves.

A `bpy.app.timers` poller is used rather than a draw handler so it keeps running
even when the viewport is not redrawing (e.g. window moved, area resized).
"""

import ctypes
import ctypes.wintypes as wt
import os

import bpy

from . import controller

_POLL_INTERVAL = 0.2     # seconds
_last_bounds = None
_blender_hwnd = None

user32 = ctypes.windll.user32


# --- locate Blender's own top-level window --------------------------------

def _find_blender_hwnd():
    """Find the GHOST window owned by this process (cached)."""
    global _blender_hwnd
    if _blender_hwnd and user32.IsWindow(_blender_hwnd):
        return _blender_hwnd

    pid = os.getpid()
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _enum(hwnd, _lparam):
        win_pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
        if win_pid.value == pid and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value.startswith("GHOST_"):
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(_enum, 0)
    _blender_hwnd = found[0] if found else None
    return _blender_hwnd


def _client_origin(hwnd):
    """Top-left of the window's client area, in desktop coordinates."""
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    rect = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    client_h = rect.bottom - rect.top
    return pt.x, pt.y, client_h


# --- region geometry -------------------------------------------------------

def _viewport_region():
    """Return (x, y, w, h) of the active 3D viewport window region, or None.

    Coordinates are Blender's: origin bottom-left of the window.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            for region in area.regions:
                if region.type == "WINDOW":
                    return region.x, region.y, region.width, region.height
    return None


def _compute_bounds():
    hwnd = _find_blender_hwnd()
    region = _viewport_region()
    if not hwnd or not region:
        return None

    rx, ry, rw, rh = region
    origin_x, origin_y, client_h = _client_origin(hwnd)

    # Blender y is from the bottom; convert region's top edge to screen-down y.
    screen_x = origin_x + rx
    screen_y = origin_y + (client_h - (ry + rh))
    return screen_x, screen_y, rw, rh


# --- poller ----------------------------------------------------------------

def _poll():
    global _last_bounds
    scene = bpy.context.scene
    if not scene or scene.webview.mode == "OFF" or not controller.is_running():
        return _POLL_INTERVAL

    bounds = _compute_bounds()
    if bounds and bounds != _last_bounds:
        _last_bounds = bounds
        x, y, w, h = bounds
        controller.send(cmd="set_bounds", x=x, y=y, w=w, h=h)
    return _POLL_INTERVAL


def register():
    if not bpy.app.timers.is_registered(_poll):
        bpy.app.timers.register(_poll, first_interval=_POLL_INTERVAL,
                                persistent=True)


def unregister():
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)
