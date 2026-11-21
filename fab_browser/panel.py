"""Sidebar panel in the 3D viewport: the Webview control surface."""

import bpy
from bpy.types import Panel

from . import controller


class VIEW3D_PT_webview(Panel):
    bl_label = "Fab Browser"
    bl_idname = "VIEW3D_PT_fab_browser"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Fab"

    def draw(self, context):
        layout = self.layout
        s = context.scene.webview

        layout.label(text="Interactive Fab page over the 3D viewport", icon="URL")
        layout.prop(s, "url", text="Fab page")

        # Active mode is the interactive in-Blender browser overlay.
        row = layout.row(align=True)
        row.prop_enum(s, "mode", "OFF", text="Hide")
        row.prop_enum(s, "mode", "ACTIVE", text="Browse Fab")

        # Background-only controls.
        col = layout.column()
        col.enabled = s.mode == "BACKGROUND"
        col.prop(s, "opacity", slider=True)
        col.prop(s, "background_interact")

        layout.separator()
        layout.label(text="Download a model in Fab, then:")
        layout.operator("fab_browser.import_latest", icon="IMPORT", text="Import Newest Download")
        layout.prop(s, "downloads_folder", text="Downloads")

        layout.separator()
        if controller.is_running():
            layout.operator("webview.stop", icon="X")
        else:
            box = layout.box()
            box.label(text="First install the WebView dependencies:", icon="INFO")
            box.operator("webview.install_deps", icon="IMPORT", text="Install WebView2 Dependencies")


def register():
    bpy.utils.register_class(VIEW3D_PT_webview)


def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_webview)
