"""Operators: dependency install + an explicit stop button."""

import subprocess
import sys
import os
import zipfile

import bpy
from bpy.types import Operator

from . import controller


class WEBVIEW_OT_install_deps(Operator):
    """Install pywebview into Blender's Python (one-time setup)."""

    bl_idname = "webview.install_deps"
    bl_label = "Install Webview Dependencies"
    bl_options = {"REGISTER"}

    def execute(self, context):
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install",
                 "pywebview", "pythonnet"]
            )
        except subprocess.CalledProcessError as err:
            self.report({"ERROR"}, f"pip install failed: {err}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Installed pywebview + pythonnet")
        return {"FINISHED"}


class WEBVIEW_OT_stop(Operator):
    """Shut down the webview window and host process."""

    bl_idname = "webview.stop"
    bl_label = "Stop Webview"
    bl_options = {"REGISTER"}

    def execute(self, context):
        context.scene.webview.mode = "OFF"
        controller.shutdown()
        return {"FINISHED"}


class FABBROWSER_OT_import_latest(Operator):
    """Import the newest supported model from Fab/Chrome downloads."""

    bl_idname = "fab_browser.import_latest"
    bl_label = "Import Newest Download"

    def execute(self, context):
        folder = bpy.path.abspath(context.scene.webview.downloads_folder)
        supported = {".zip", ".fbx", ".glb", ".gltf", ".obj"}
        try:
            files = [(e.stat().st_mtime, e.path) for e in os.scandir(folder)
                     if e.is_file() and os.path.splitext(e.name)[1].lower() in supported]
            if not files:
                raise RuntimeError("No supported model download found in this folder.")
            _, path = max(files)
            ext = os.path.splitext(path)[1].lower()
            models = [path]
            if ext == ".zip":
                root = os.path.join(bpy.utils.user_resource('DATAFILES'), "fab_browser", "downloads",
                                    os.path.splitext(os.path.basename(path))[0])
                os.makedirs(root, exist_ok=True)
                root_abs = os.path.abspath(root)
                with zipfile.ZipFile(path) as archive:
                    for member in archive.infolist():
                        target = os.path.abspath(os.path.join(root_abs, member.filename))
                        if target != root_abs and not target.startswith(root_abs + os.sep):
                            raise RuntimeError("Archive contains an unsafe path.")
                        archive.extract(member, root_abs)
                rank = {".fbx": 0, ".glb": 1, ".gltf": 2, ".obj": 3}
                models = [(rank[os.path.splitext(f)[1].lower()], os.path.join(d, f))
                          for d, _, names in os.walk(root_abs) for f in names
                          if os.path.splitext(f)[1].lower() in rank]
                if not models:
                    raise RuntimeError("ZIP contains no FBX, GLB, glTF, or OBJ model.")
                path = min(models)[1]
                ext = os.path.splitext(path)[1].lower()
            if ext == ".fbx":
                bpy.ops.import_scene.fbx(filepath=path)
            elif ext in {".glb", ".gltf"}:
                bpy.ops.import_scene.gltf(filepath=path)
            elif ext == ".obj":
                if hasattr(bpy.ops.wm, "obj_import"):
                    bpy.ops.wm.obj_import(filepath=path)
                else:
                    bpy.ops.import_scene.obj(filepath=path)
            else:
                raise RuntimeError("This download format is not supported for scene import.")
            self.report({"INFO"}, "Imported " + os.path.basename(path))
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc)[:220])
            return {"CANCELLED"}


_CLASSES = (WEBVIEW_OT_install_deps, WEBVIEW_OT_stop, FABBROWSER_OT_import_latest)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
