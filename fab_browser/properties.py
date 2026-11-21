"""Scene-level settings for the webview overlay.

Changing any of these via the panel triggers an `update` callback that pushes the
new state to the running host process through the controller. That is the single
place where UI state turns into IPC commands.
"""

import bpy
import os
from bpy.props import (
    EnumProperty,
    FloatProperty,
    BoolProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

from . import controller


# --- update callbacks ------------------------------------------------------
# Each callback forwards the *whole* relevant state so the host never has to
# guess. They are cheap no-ops when the host is not running.

def _on_mode(self, context):
    if self.mode != "OFF":
        controller.ensure_running(self.url)
    controller.send(
        cmd="set_mode",
        mode=self.mode.lower(),
        opacity=self.opacity,
        interact=self.background_interact,
    )
    if self.mode == "OFF":
        controller.send(cmd="hide")


def _on_opacity(self, context):
    controller.send(cmd="set_opacity", value=self.opacity)


def _on_interact(self, context):
    controller.send(cmd="set_interact", value=self.background_interact)


def _on_url(self, context):
    controller.send(cmd="set_url", url=self.url)


class WebviewSettings(PropertyGroup):
    mode: EnumProperty(
        name="Mode",
        description="Webview overlay mode",
        items=(
            ("OFF", "Off", "Hide the webview"),
            ("ACTIVE", "Active",
             "Interactive, always-on-top, draggable window"),
            ("BACKGROUND", "Background",
             "Transparent, click-through overlay tracking the 3D viewport"),
        ),
        default="OFF",
        update=_on_mode,
    )

    opacity: FloatProperty(
        name="Opacity",
        description="Webview opacity in background mode",
        default=0.35,
        min=0.05,
        max=1.0,
        subtype="FACTOR",
        update=_on_opacity,
    )

    background_interact: BoolProperty(
        name="Allow keys (background)",
        description="In background mode, forward arrow keys and Space to the "
                    "webview so you can control YouTube playback. May interfere "
                    "with animation playback shortcuts while enabled",
        default=False,
        update=_on_interact,
    )

    url: StringProperty(
        name="Fab URL",
        description="Fab page shown over the Blender viewport",
        default="https://www.fab.com/",
        update=_on_url,
    )

    downloads_folder: StringProperty(
        name="Downloads folder",
        subtype="DIR_PATH",
        default=os.path.join(os.path.expanduser("~"), "Downloads"),
    )


def register():
    bpy.utils.register_class(WebviewSettings)
    bpy.types.Scene.webview = bpy.props.PointerProperty(type=WebviewSettings)


def unregister():
    del bpy.types.Scene.webview
    bpy.utils.unregister_class(WebviewSettings)
