"""Fab Browser: open the real Fab site and import its downloaded 3D assets."""

bl_info = {
    "name": "Fab Browser",
    "author": "Fab to Blender community",
    "version": (2026, 2, 0),
    "blender": (4, 4, 0),
    "location": "3D View > Sidebar > Fab",
    "description": "Browse Fab in Chrome and import downloaded assets into Blender",
    "category": "3D View",
}

import bpy
import os
import subprocess
import urllib.parse
import webbrowser
import zipfile
from bpy.props import StringProperty


def _chrome_executable():
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", "C:/Program Files"), "Google/Chrome/Application/chrome.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"), "Google/Chrome/Application/chrome.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google/Chrome/Application/chrome.exe"),
    ]
    return next((path for path in candidates if path and os.path.isfile(path)), None)


def _fab_search_url(query):
    if query.strip():
        return "https://www.fab.com/search?" + urllib.parse.urlencode({"q": query.strip()})
    return "https://www.fab.com/"


def _open_fab(url):
    """Open the actual site in Chrome, using its normal signed-in profile."""
    chrome = _chrome_executable()
    if chrome:
        subprocess.Popen([chrome, "--new-window", url], close_fds=True)
    else:
        webbrowser.open(url, new=1)


class FABBROWSER_PG_settings(bpy.types.PropertyGroup):
    query: StringProperty(name="Search Fab", default="")
    downloads_folder: StringProperty(
        name="Chrome Downloads", subtype='DIR_PATH',
        default=os.path.join(os.path.expanduser("~"), "Downloads"),
    )


class FABBROWSER_OT_open_store(bpy.types.Operator):
    bl_idname = "fab_browser.open_store"
    bl_label = "Browse Fab in Chrome"
    bl_description = "Open the real Fab website in Chrome with your normal browser profile and login"

    def execute(self, context):
        query = context.scene.fab_browser.query
        _open_fab(_fab_search_url(query))
        self.report({'INFO'}, "Fab opened in Chrome. Download an asset there, then import it here.")
        return {'FINISHED'}


def _safe_extract(archive_path, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    root = os.path.abspath(target_dir)
    root_prefix = root + os.sep
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            destination = os.path.abspath(os.path.join(root, member.filename))
            if destination != root and not destination.startswith(root_prefix):
                raise RuntimeError("The downloaded archive contains an unsafe path.")
            archive.extract(member, root)


def _import_model(path):
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
        raise RuntimeError("Choose a Fab FBX, GLB, glTF, OBJ, or ZIP download.")


class FABBROWSER_OT_import_latest(bpy.types.Operator):
    bl_idname = "fab_browser.import_latest"
    bl_label = "Import Newest Fab Download"
    bl_description = "Import the most recently downloaded supported 3D asset from Chrome Downloads"

    def execute(self, context):
        folder = bpy.path.abspath(context.scene.fab_browser.downloads_folder)
        if not os.path.isdir(folder):
            self.report({'ERROR'}, "Downloads folder does not exist. Set the folder below.")
            return {'CANCELLED'}

        supported = {".zip", ".fbx", ".glb", ".gltf", ".obj"}
        candidates = []
        for entry in os.scandir(folder):
            if entry.is_file() and os.path.splitext(entry.name)[1].lower() in supported:
                candidates.append((entry.stat().st_mtime, entry.path))
        if not candidates:
            self.report({'ERROR'}, "No FBX, GLB, glTF, OBJ, or ZIP found in the selected Downloads folder.")
            return {'CANCELLED'}

        _, newest = max(candidates)
        try:
            ext = os.path.splitext(newest)[1].lower()
            if ext != ".zip":
                _import_model(newest)
            else:
                import_root = os.path.join(
                    bpy.utils.user_resource('DATAFILES'), "fab_browser", "downloads",
                    os.path.splitext(os.path.basename(newest))[0],
                )
                _safe_extract(newest, import_root)
                rank = {".fbx": 0, ".glb": 1, ".gltf": 2, ".obj": 3}
                models = []
                for directory, _, filenames in os.walk(import_root):
                    for filename in filenames:
                        file_path = os.path.join(directory, filename)
                        file_ext = os.path.splitext(filename)[1].lower()
                        if file_ext in rank:
                            models.append((rank[file_ext], file_path))
                if not models:
                    raise RuntimeError("The newest ZIP has no FBX, GLB, glTF, or OBJ model.")
                _import_model(min(models)[1])
            self.report({'INFO'}, "Imported " + os.path.basename(newest))
        except Exception as exc:
            self.report({'ERROR'}, str(exc)[:220])
            return {'CANCELLED'}
        return {'FINISHED'}


class FABBROWSER_PT_panel(bpy.types.Panel):
    bl_label = "Fab Browser"
    bl_idname = "FABBROWSER_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Fab"

    def draw(self, context):
        layout = self.layout
        props = context.scene.fab_browser
        layout.label(text="Fab's full website opens in Chrome.", icon='INFO')
        layout.label(text="Your Chrome login, images, filters, and product pages work there.")
        layout.prop(props, "query", text="Search")
        layout.operator("fab_browser.open_store", icon='URL', text="Browse Fab in Chrome")
        layout.separator()
        layout.label(text="After downloading a 3D asset on Fab:")
        layout.operator("fab_browser.import_latest", icon='IMPORT', text="Import Newest Fab Download")
        layout.prop(props, "downloads_folder", text="Downloads")


_CLASSES = (
    FABBROWSER_PG_settings,
    FABBROWSER_OT_open_store,
    FABBROWSER_OT_import_latest,
    FABBROWSER_PT_panel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.fab_browser = bpy.props.PointerProperty(type=FABBROWSER_PG_settings)


def unregister():
    del bpy.types.Scene.fab_browser
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
