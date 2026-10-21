"""Run inside Blender to guard the actual native-driver and blink outputs."""

import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_characters import StudioCharacter


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for kind, expected in (("snow", 1070), ("rain", 514)):
        actor = StudioCharacter("native_loader_" + kind, (0, 0, 0), 0, kind, (0.1, 0.2, 0.3))
        if len(actor.rig.animation_data.drivers) != expected:
            raise RuntimeError(f"Source animation cleanup removed native {kind} drivers.")
        if actor.rig.animation_data.action is not None:
            raise RuntimeError(f"Source performance was not cleared on {kind}.")
        actor.face(None, 0.49, 1, 0, False)
        bpy.context.scene.frame_set(1)
        actor.rig.update_tag()
        bpy.context.view_layer.update()
        invalid = [curve.data_path for curve in actor.rig.animation_data.drivers if not curve.driver.is_valid]
        if invalid:
            raise RuntimeError(f"Invalid {kind} source drivers: {invalid[:5]}")
        if kind == "snow":
            close = next(constraint for constraint in actor.bones["Eyelid_Upper3.L"].constraints
                         if constraint.type == "ACTION" and "CloseOpen" in constraint.name)
            value = close.eval_time
        else:
            head = next(obj for obj in actor.root.children_recursive
                        if obj.type == "MESH" and obj.name.startswith("GEO-rain-head"))
            value = head.data.shape_keys.key_blocks["EyelidsClose.L"].value
        if value < 0.98:
            raise RuntimeError(f"The standard {kind} blink did not close the actual eyelid: {value}")
        print(f"Native-loader check passed: {kind}, {expected} valid drivers, actual blink output {value:.3f}")


if __name__ == "__main__":
    main()
