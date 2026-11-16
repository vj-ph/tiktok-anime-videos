"""Optional Swiss room props adapted from the recorded public-domain/CC0 assets."""

import math
from pathlib import Path


def add_flags(scene, assets):
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
    from build_scene import box, material
    from prepare_audio import sha256_file

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=assets["model"])
    imported = set(bpy.data.objects) - before
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(meshes) != 1:
        raise ValueError("The recorded Quaternius flag must import as one mesh.")
    flag = meshes[0]
    transform = flag.matrix_world.copy()
    flag.parent = None
    flag.data.transform(transform)
    flag.matrix_world = Matrix.Identity(4)
    for obj in imported - {flag}:
        bpy.data.objects.remove(obj, do_unlink=True)
    cloth = {index for face in flag.data.polygons
             if flag.data.materials[face.material_index].name.startswith("LightRed")
             for index in face.vertices}
    if not cloth:
        raise ValueError("Imported flag cloth material is missing.")
    x0 = min(flag.data.vertices[i].co.x for i in cloth)
    z0 = min(flag.data.vertices[i].co.z for i in cloth)
    z1 = max(flag.data.vertices[i].co.z for i in cloth)
    side = (z1 - z0) * 1.5
    cloth_material = next(face.material_index for face in flag.data.polygons
                          if any(i in cloth for i in face.vertices))
    mesh = bmesh.new()
    mesh.from_mesh(flag.data)
    mesh.verts.ensure_lookup_table()
    bmesh.ops.delete(mesh, geom=[mesh.verts[i] for i in cloth], context="VERTS")
    face = mesh.faces.new([mesh.verts.new(co) for co in (
        (x0, 0, z1 - side), (x0 + side, 0, z1 - side),
        (x0 + side, 0, z1), (x0, 0, z1))])
    face.material_index = cloth_material
    mesh.to_mesh(flag.data)
    mesh.free()
    uv = flag.data.uv_layers.new(name="Swiss projected artwork")
    for face in flag.data.polygons:
        for loop_index in face.loop_indices:
            vertex = flag.data.vertices[flag.data.loops[loop_index].vertex_index]
            uv.data[loop_index].uv = ((vertex.co.x - x0) / side, (vertex.co.z - (z1 - side)) / side)

    image = bpy.data.images.load(assets["texture"], check_existing=True)
    image.colorspace_settings.name = "sRGB"
    image.pack()
    print_mat = material("Swiss flag printed cloth", (.8, .01, .01), .85)
    nodes, links = print_mat.node_tree.nodes, print_mat.node_tree.links
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    texture.extension = "EXTEND"
    links.new(texture.outputs["Color"], nodes.get("Principled BSDF").inputs["Base Color"])
    metal = material("Swiss desk flag brushed metal", (.18, .2, .22), .35)
    metal.node_tree.nodes.get("Principled BSDF").inputs["Metallic"].default_value = .7
    for index, slot in enumerate(flag.data.materials):
        flag.data.materials[index] = print_mat if slot.name.startswith("LightRed") else metal
    table = scene.objects["Exam table"]
    surface = max((table.matrix_world @ Vector(corner)).z for corner in table.bound_box)
    minimum = min(vertex.co.z for vertex in flag.data.vertices)
    height = max(vertex.co.z for vertex in flag.data.vertices) - minimum
    for vertex in flag.data.vertices:
        vertex.co.z -= minimum
    flag.name = "Swiss table flag"
    flag.scale = (.38 / height,) * 3
    flag.rotation_mode = "XYZ"
    flag.rotation_euler.z = math.pi / 2
    flag.location = (.45, -.35, surface + .015)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=.045, depth=.015,
                                      location=(.45, -.35, surface + .0075))
    bpy.context.object.name = "Swiss table flag stand"
    bpy.context.object.data.materials.append(metal)
    box("Swiss wall flag mount", (-3.90, -2.0, 1.25), (.035, .58, .58), metal, .008)
    bpy.ops.mesh.primitive_plane_add(size=.55, location=(-3.875, -2.0, 1.25),
                                    rotation=(0, math.pi / 2, 0))
    wall = bpy.context.object
    wall.name = "Swiss wall flag"
    wall.data.materials.append(print_mat)
    for obj in (flag, wall):
        obj["flag_texture_sha256"] = sha256_file(Path(assets["texture"]))
    flag["source_model_sha256"] = sha256_file(Path(assets["model"]))
    flag["cloth_side_m"] = side * flag.scale.x
    flag.data.update()
    bpy.context.view_layer.update()


def inspect_flags(scene, cameras):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from b2_speaking import shared_head_fits
    from mathutils import Vector

    if "Swiss table flag" not in scene.objects:
        return None
    result = {}
    camera = cameras["wide"]
    graph = bpy.context.evaluated_depsgraph_get()
    for name in ("Swiss table flag", "Swiss wall flag"):
        obj = scene.objects[name]
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        projected = [world_to_camera_view(scene, camera, point) for point in points]
        bounds = [min(p.x for p in projected), min(p.y for p in projected),
                  max(p.x for p in projected), max(p.y for p in projected)]
        if not shared_head_fits({"bounds": bounds, "in_front": all(p.z > 0 for p in projected)}):
            raise ValueError(f"{name}: outside shared wide-camera crop: {bounds}")
        visible_faces = 0
        for face in obj.data.polygons:
            if obj.data.materials[face.material_index].name != "Swiss flag printed cloth":
                continue
            point = obj.matrix_world @ face.center
            direction = point - camera.location
            hit, _, _, _, obstruction, _ = scene.ray_cast(graph, camera.location,
                                                          direction.normalized(), distance=direction.length + .01)
            if hit and obstruction.original == obj:
                visible_faces += 1
        if not visible_faces:
            raise ValueError(f"{name}: cloth is occluded from the wide camera.")
        result[name] = {"wide_bounds": bounds, "visible_cloth_faces": visible_faces,
                        "texture_sha256": obj["flag_texture_sha256"]}
    return result
