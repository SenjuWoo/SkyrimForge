"""Runs inside headless Blender: blender -b --factory-startup --python nif_blender.py -- <mode> <addon dir> <in> <out>.

Enables PyNifly from its folder with addon_utils.enable for this process only (preferences are never saved),
so nothing is installed into the user's Blender. Prints one line: SKYRIMFORGE_RESULT {json}.
"""
import json
import os
import sys
import traceback


def main():
    mode, addon_dir, source, output = sys.argv[sys.argv.index("--") + 1:][:4]
    import addon_utils
    import bpy
    if mode in ("import", "roundtrip"):
        bpy.ops.wm.read_factory_settings(use_empty=True)  # before enabling: a factory reset drops add-ons
    else:
        bpy.ops.wm.open_mainfile(filepath=source, load_ui=False)
    bpy.context.preferences.use_preferences_save = False
    sys.path.insert(0, addon_dir)
    if addon_utils.enable("io_scene_nifly", default_set=True, persistent=False) is None:
        raise RuntimeError("PyNifly could not be enabled from " + addon_dir)
    if mode in ("import", "roundtrip"):
        result = bpy.ops.import_scene.pynifly(filepath=source)
        if "FINISHED" not in result:
            raise RuntimeError(f"import returned {result}")
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if mode == "import":
        bpy.ops.wm.save_as_mainfile(filepath=output)
    else:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in meshes:
            obj.select_set(True)
        if meshes:
            bpy.context.view_layer.objects.active = meshes[0]
        result = bpy.ops.export_scene.pynifly(filepath=output, target_game="SKYRIMSE")
        # PyNifly returns an empty set after a successful export, so the written file is the evidence.
        if "CANCELLED" in result or not os.path.isfile(output):
            raise RuntimeError(f"export returned {result} and wrote no file")
    return {"ok": True, "meshes": len(meshes), "objects": len(bpy.context.scene.objects), "blender": bpy.app.version_string}


try:
    payload = main()
except Exception as exc:  # every failure comes back as JSON
    payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-800:]}
print("SKYRIMFORGE_RESULT " + json.dumps(payload), flush=True)
