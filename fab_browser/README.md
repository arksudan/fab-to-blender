# Fab Browser v2026.2

Fab Browser is based on [blender-webview](https://github.com/nawat-john/blender-webview). It displays the real Fab website in an interactive WebView2 overlay aligned over Blender's 3D viewport, with a small browser navigation bar.

## Requirements

- Windows 10/11
- Blender 5.0 or newer
- Microsoft Edge WebView2 Runtime
- `pywebview` and `pythonnet` installed into Blender's Python (use the panel button once)

## Install and use

1. Install `fab_browser_v2026_webview.zip` from **Edit → Preferences → Add-ons → Install from Disk**, then enable Fab Browser.
2. Open **3D View → Sidebar (N) → Fab**. Click **Install WebView2 Dependencies** once if shown.
3. Click **Browse Fab**. Fab appears over the 3D viewport; use the web toolbar to browse, sign in, and download an asset.
4. Return to Blender and click **Import Newest Download**. The add-on looks in the Downloads folder shown in the panel and imports FBX, GLB, glTF, or OBJ, including those inside a ZIP.

The browser is a separate WebView2 window positioned over the viewport, because Blender add-on panels cannot render HTML themselves. The window is interactive and uses Fab's regular website for images, login, and browsing. WebView2 uses its own browser profile; sign in to Fab in the overlay once if needed.
