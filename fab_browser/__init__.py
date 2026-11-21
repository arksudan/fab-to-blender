"""Blender Webview add-on.

Overlays a borderless WebView2 window (rendered by a separate `webview_host`
process) on top of Blender, and remote-controls its mode, opacity, click-through
behaviour and bounds from a panel in the 3D viewport sidebar.

Windows only. See CLAUDE.md for the architecture.
"""

bl_info = {
    "name": "Fab Browser",
    "author": "Fab to Blender community (based on blender-webview)",
    "version": (2026, 2, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar (N) > Fab",
    "description": "Browse Fab inside the Blender viewport and import downloaded models",
    "warning": "Windows only. Requires pywebview + pythonnet and WebView2 Runtime.",
    "category": "3D View",
}

from . import properties, controller, operators, panel, viewport

# Order matters: properties first (others reference them), UI last.
_MODULES = (properties, controller, operators, panel, viewport)


def register():
    for mod in _MODULES:
        if hasattr(mod, "register"):
            mod.register()


def unregister():
    # Make sure the external process is shut down before classes vanish.
    controller.shutdown()
    for mod in reversed(_MODULES):
        if hasattr(mod, "unregister"):
            mod.unregister()
