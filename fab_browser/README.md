# Fab Browser v2026

Fab Browser opens the actual Fab website in a regular Chrome window. Fab handles its own login, images, filters, listing pages, library, and downloads using the Chrome profile already configured on the computer.

## Install

In Blender, open **Edit → Preferences → Add-ons → Install from Disk**, choose `fab_browser_v2026.zip`, enable **Fab Browser**, then open **3D View → Sidebar (N) → Fab**.

## Use

1. Enter an optional search term and click **Browse Fab in Chrome**.
2. Browse Fab and sign in normally in Chrome if needed. Download a 3D model in FBX, GLB, glTF, OBJ, or ZIP format.
3. Return to Blender and click **Import Newest Fab Download**. The add-on imports the newest supported file from the Downloads folder shown in its panel. Change that folder if Chrome saves elsewhere.

Blender does not include an embedded Chromium engine for add-ons, so the actual site runs in Chrome rather than being drawn inside Blender. This gives Fab's normal website features and account session without copying browser credentials into the add-on. The import button handles downloaded model files; materials and other non-model assets may need their own import workflow.
