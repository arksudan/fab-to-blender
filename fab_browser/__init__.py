"""Fab Browser: a standalone Fab marketplace browser for Blender."""

bl_info = {
    "name": "Fab Browser",
    "author": "Fab to Blender community",
    "version": (2026, 1, 0),
    "blender": (4, 4, 0),
    "location": "3D View > Sidebar > Fab",
    "description": "Browse the public Fab catalog and add supported 3D assets to a scene",
    "category": "3D View",
}

import bpy
import bpy.utils.previews
import json
import os
import threading
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import tempfile
import shutil
from bpy.props import StringProperty, EnumProperty, IntProperty

API = "https://www.fab.com/i"
_state = {"items": [], "next": None, "loading": False, "error": "", "thumbs": 0, "lock": threading.Lock()}
_previews = None
_cache_dir = ""


def _get_json(url):
    request = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "Mozilla/5.0 FabBrowser/2026",
        "Referer": "https://www.fab.com/",
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def _image_url(item):
    for thumb in item.get("thumbnails", []):
        images = thumb.get("images", [])
        if images:
            return min(images, key=lambda img: abs(int(img.get("height", 240)) - 240)).get("url", "")
    return ""


def _download_thumbnails(rows):
    folder = _cache_dir
    for item in rows:
        url = item.get("image", "")
        if not url:
            continue
        path = os.path.join(folder, item["uid"] + ".jpg")
        try:
            if not os.path.exists(path):
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=15) as response, open(path, "wb") as out:
                    shutil.copyfileobj(response, out)
            item["image_path"] = path
        except Exception:
            item["image_path"] = ""
        with _state["lock"]:
            _state["thumbs"] -= 1


def _redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
    return None


def _refresh_timer():
    if _state["thumbs"]:
        _redraw()
        return 0.5
    return 1.0


def _search_worker(query, kind, sort, cursor):
    try:
        params = {"currency": "USD", "count": "30", "sort_by": sort}
        if query.strip():
            params["q"] = query.strip()
        if kind != "all":
            params["listing_types"] = kind
        if cursor:
            params["cursor"] = cursor
        data = _get_json(API + "/listings/search?" + urllib.parse.urlencode(params))
        rows = []
        for entry in data.get("results", []):
            type_value = entry.get("listingType") or entry.get("listing_type") or entry.get("type") or {}
            if isinstance(type_value, dict):
                type_value = type_value.get("code") or type_value.get("name") or ""
            rows.append({
                "uid": entry.get("uid", ""),
                "title": entry.get("title", "Untitled asset"),
                "seller": (entry.get("seller") or {}).get("name", "Fab seller"),
                "kind": str(type_value),
                "price": entry.get("price", {}).get("price", ""),
                "url": "https://www.fab.com/listings/" + entry.get("uid", ""),
                "image": _image_url(entry),
            })
        with _state["lock"]:
            if not cursor:
                _state["items"] = rows
            else:
                _state["items"].extend(rows)
            _state["next"] = (data.get("cursors") or {}).get("next")
            _state["error"] = ""
        with _state["lock"]:
            _state["thumbs"] += len(rows)
        threading.Thread(target=_download_thumbnails, args=(rows,), daemon=True).start()
    except Exception as exc:
        with _state["lock"]:
            _state["error"] = str(exc)[:220]
    finally:
        _state["loading"] = False


def _start_search(context, more=False):
    if _state["loading"]:
        return
    _state["loading"] = True
    _state["error"] = ""
    props = context.scene.fab_browser
    cursor = _state["next"] if more else None
    threading.Thread(target=_search_worker,
                     args=(props.query, props.kind, props.sort, cursor), daemon=True).start()


class FABBROWSER_PG_settings(bpy.types.PropertyGroup):
    query: StringProperty(name="Search", default="")
    kind: EnumProperty(name="Type", items=[
        ("all", "All assets", "Search every Fab listing type"),
        ("3d-model", "3D models", ""), ("material", "Materials", ""),
        ("environment", "Environments", ""), ("hdri", "HDRIs", ""),
        ("decal", "Decals", ""), ("audio", "Audio", ""),
        ("2d-asset", "2D assets", ""), ("code-plugin", "Code/plugins", ""),
    ], default="all")
    sort: EnumProperty(name="Sort", items=[
        ("-relevance", "Relevance", ""), ("-createdAt", "Newest", ""),
        ("-price", "Price: high to low", ""), ("price", "Price: low to high", ""),
    ], default="-relevance")
    selected: IntProperty(default=-1)


class FABBROWSER_OT_search(bpy.types.Operator):
    bl_idname = "fab_browser.search"
    bl_label = "Search Fab"
    more: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        if not self.more:
            _state["next"] = None
        _start_search(context, self.more)
        return {'FINISHED'}


class FABBROWSER_OT_open(bpy.types.Operator):
    bl_idname = "fab_browser.open_listing"
    bl_label = "Open on Fab"
    url: StringProperty()

    def execute(self, context):
        webbrowser.open(self.url)
        return {'FINISHED'}


def _download_and_import(uid, title):
    safe_name = "".join(c for c in title if c.isalnum() or c in " -_").strip() or uid
    root = os.path.join(bpy.utils.user_resource('DATAFILES'), "fab_browser", uid)
    os.makedirs(root, exist_ok=True)
    formats = _get_json(API + "/listings/" + uid + "/asset-formats")
    choices = {"fbx", "glb", "gltf", "obj"}
    selected = None
    for fmt in formats if isinstance(formats, list) else []:
        code = ((fmt.get("assetFormatType") or {}).get("code") or "").lower()
        if code in choices and fmt.get("files"):
            selected = (code, fmt["files"][0])
            break
    if not selected:
        raise RuntimeError("No FBX, GLB, glTF, or OBJ download is listed for this asset.")
    code, file_info = selected
    file_uid = file_info.get("uid")
    filename = os.path.basename(file_info.get("name") or (uid + ".zip"))
    target = os.path.join(root, filename)
    info = _get_json(API + f"/listings/{uid}/asset-formats/{urllib.parse.quote(code)}/files/{file_uid}/download-info")
    download_url = info["downloadInfo"][0]["downloadUrl"]
    if not os.path.exists(target):
        request = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=120) as response, open(target, "wb") as out:
            shutil.copyfileobj(response, out)
    paths = []
    if zipfile.is_zipfile(target):
        extract = os.path.join(root, "extracted")
        os.makedirs(extract, exist_ok=True)
        with zipfile.ZipFile(target) as archive:
            base = os.path.abspath(extract) + os.sep
            for member in archive.infolist():
                destination = os.path.abspath(os.path.join(extract, member.filename))
                if destination != os.path.abspath(extract) and not destination.startswith(base):
                    raise RuntimeError("Archive contains an unsafe file path.")
                archive.extract(member, extract)
        paths = [os.path.join(dp, f) for dp, _, files in os.walk(extract) for f in files]
    else:
        paths = [target]
    imported = False
    for path in paths:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=path); imported = True
        elif ext in {".glb", ".gltf"}:
            bpy.ops.import_scene.gltf(filepath=path); imported = True
        elif ext == ".obj":
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(filepath=path)
            else:
                bpy.ops.import_scene.obj(filepath=path)
            imported = True
        if imported:
            break
    if not imported:
        raise RuntimeError("Downloaded files did not contain an importable FBX, GLB, glTF, or OBJ.")


class FABBROWSER_OT_add(bpy.types.Operator):
    bl_idname = "fab_browser.add_to_scene"
    bl_label = "Download & Add to Scene"
    uid: StringProperty()
    title: StringProperty()

    def execute(self, context):
        try:
            _download_and_import(self.uid, self.title)
            self.report({'INFO'}, "Asset added to the scene")
        except Exception as exc:
            self.report({'ERROR'}, str(exc)[:200])
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
        row = layout.row(align=True)
        row.prop(props, "query", text="", icon='VIEWZOOM')
        row.operator("fab_browser.search", text="", icon='FILE_REFRESH')
        row = layout.row(align=True)
        row.prop(props, "kind", text="")
        row.prop(props, "sort", text="")
        if _state["loading"]:
            layout.label(text="Loading Fab catalog…", icon='TIME')
        if _state["error"]:
            layout.label(text=_state["error"], icon='ERROR')
        with _state["lock"]:
            items = list(_state["items"])
        if not items and not _state["loading"]:
            layout.label(text="Search all Fab listings, then select an asset.")
        for index, item in enumerate(items):
            box = layout.box()
            row = box.row(align=True)
            if item.get("image_path") and _previews:
                key = item["uid"]
                if key not in _previews:
                    try:
                        _previews.load(key, item["image_path"], 'IMAGE')
                    except Exception:
                        pass
                if key in _previews:
                    row.template_icon(_previews[key].icon_id, scale=5)
            col = row.column(align=True)
            col.label(text=item["title"][:56])
            col.label(text=(item["seller"] + " · " + item["kind"])[:56])
            actions = col.row(align=True)
            actions.operator("fab_browser.open_listing", text="View", icon='URL').url = item["url"]
            add = actions.operator("fab_browser.add_to_scene", text="Add", icon='IMPORT')
            add.uid, add.title = item["uid"], item["title"]
        if _state["next"]:
            op = layout.operator("fab_browser.search", text="Load more results", icon='TRIA_DOWN')
            op.more = True


_CLASSES = (FABBROWSER_PG_settings, FABBROWSER_OT_search, FABBROWSER_OT_open,
            FABBROWSER_OT_add, FABBROWSER_PT_panel)


def register():
    global _previews, _cache_dir
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.fab_browser = bpy.props.PointerProperty(type=FABBROWSER_PG_settings)
    _previews = bpy.utils.previews.new()
    _cache_dir = os.path.join(bpy.utils.user_resource('CACHE'), "fab_browser")
    bpy.app.timers.register(_refresh_timer, first_interval=1.0)


def unregister():
    global _previews
    if _previews:
        bpy.utils.previews.remove(_previews)
        _previews = None
    if bpy.app.timers.is_registered(_refresh_timer):
        bpy.app.timers.unregister(_refresh_timer)
    del bpy.types.Scene.fab_browser
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
