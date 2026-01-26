import bpy
import math
import random
import os
from mathutils import Vector

bl_info = {
    "name": "Cinematic Director",
    "location": "View3D > Sidebar > Cinematic",
}


class CinematicUtils:
    @staticmethod
    def setup_scene_basics(context, use_ground=True):
        if use_ground and not bpy.data.objects.get("Cinematic_Ground"):
            bpy.ops.mesh.primitive_grid_add(size=200, location=(0, 0, -0.05))
            ground = context.active_object
            ground.name = "Cinematic_Ground"
            ground.hide_select = True
            mat = bpy.data.materials.new("Ground_Mat")
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.05, 0.05, 0.05, 1)
                bsdf.inputs["Roughness"].default_value = 0.9
            ground.data.materials.append(mat)

    @staticmethod
    def setup_hdri_skybox(context, image_path):
        if not image_path or not os.path.exists(image_path):
            return
        world = context.scene.world
        if not world:
            world = bpy.data.worlds.new("CinematicWorld")
            context.scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()
        node_env = nodes.new(type="ShaderNodeTexEnvironment")
        node_env.location = (-300, 0)
        try:
            node_env.image = bpy.data.images.load(image_path)
        except:
            pass
        node_bg = nodes.new(type="ShaderNodeBackground")
        node_bg.location = (0, 0)
        node_out = nodes.new(type="ShaderNodeOutputWorld")
        node_out.location = (300, 0)
        links.new(node_env.outputs["Color"], node_bg.inputs["Color"])
        links.new(node_bg.outputs["Background"], node_out.inputs["Surface"])

    @staticmethod
    def cleanup():
        to_delete = []
        for obj in bpy.data.objects:
            if "Master_Camera_Rig" in obj.name:
                to_delete.append(obj)

        if to_delete:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in to_delete:
                obj.select_set(True)
            bpy.ops.object.delete()

        for cam in bpy.data.cameras:
            if cam.users == 0:
                bpy.data.cameras.remove(cam)

    @staticmethod
    def get_tracking_target(obj):
        target_obj = obj
        bone_name = None

        if obj.parent and obj.parent.type == "ARMATURE":
            armature = obj.parent
            target_obj = armature
            if "Pelvis" in armature.data.bones:
                bone_name = "Pelvis"

            # Fallback gdy nie znajdzie środka
            if not bone_name and armature.data.bones:
                bone_name = armature.data.bones[0].name

        return target_obj, bone_name

    @staticmethod
    def setup_camera_system(context, input_obj, radius=7.0):
        CinematicUtils.cleanup()

        real_target, bone_name = CinematicUtils.get_tracking_target(input_obj)

        bpy.ops.object.camera_add(
            enter_editmode=False,
            align="VIEW",
            location=(0, 0, 0),
            rotation=(1.01799, 6.77293e-07, 0.784868),
            scale=(1, 1, 1),
        )
        rig = context.active_object
        rig.name = "Master_Camera_Rig"

        bpy.ops.object.select_all(action="DESELECT")
        rig.select_set(True)
        context.view_layer.objects.active = rig
        context.scene.camera = rig

        try:
            rig.camera_type = "MESH"
            rig.pattern_type = "ORBIT"
            rig.target_object = real_target.name
            rig.radius = radius
        except:
            pass

        context.view_layer.update()

        try:
            bpy.ops.multicam.set_mesh_cameras()
        except:
            return []

        context.view_layer.update()

        const = rig.constraints.new(type="COPY_LOCATION")
        const.target = real_target
        if bone_name:
            const.subtarget = bone_name
        const.influence = 1.0

        children_cameras = [child for child in rig.children if child.type == "CAMERA"]

        for cam in children_cameras:
            if cam.location.length > 0:
                cam.location = cam.location.normalized() * radius

            has_track = False
            for c in cam.constraints:
                if c.type == "TRACK_TO":
                    c.target = real_target
                    if bone_name:
                        c.subtarget = bone_name
                    has_track = True

            if not has_track:
                tt = cam.constraints.new(type="TRACK_TO")
                tt.target = real_target
                if bone_name:
                    tt.subtarget = bone_name
                tt.track_axis = "TRACK_NEGATIVE_Z"
                tt.up_axis = "UP_Y"

        return children_cameras

    @staticmethod
    def get_world_position(obj, bone_name=None):
        if bone_name and obj.type == "ARMATURE":
            try:
                bone = obj.pose.bones[bone_name]
                return obj.matrix_world @ bone.head
            except:
                return obj.matrix_world.translation
        return obj.matrix_world.translation

    @staticmethod
    def check_occlusion(scene, camera, real_target, bone_name, frame_num):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        origin = camera.matrix_world.translation

        base_pos = CinematicUtils.get_world_position(real_target, bone_name)

        target_center = base_pos + Vector((0, 0, 0.5))

        direction = (target_center - origin).normalized()
        distance = (target_center - origin).length

        is_hit, hit_loc, hit_normal, hit_index, hit_obj, matrix = scene.ray_cast(
            depsgraph, origin, direction, distance=distance - 0.5
        )

        if is_hit:
            if hit_obj.name == "Cinematic_Ground" or hit_obj == real_target:
                return False
            if hit_obj.parent == real_target:
                return False

            return True
        return False

    @staticmethod
    def run_director_logic(context, cameras, input_obj, start, end):
        scene = context.scene
        scene.timeline_markers.clear()
        if not cameras:
            return

        real_target, bone_name = CinematicUtils.get_tracking_target(input_obj)

        current_cam = cameras[0]
        m = scene.timeline_markers.new("Start", frame=start)
        m.camera = current_cam

        for f in range(start, end + 1):
            scene.frame_set(f)
            context.view_layer.update()

            is_occluded = CinematicUtils.check_occlusion(
                scene, current_cam, real_target, bone_name, f
            )

            if is_occluded:
                candidates = []
                for c in cameras:
                    if c == current_cam:
                        continue
                    if not CinematicUtils.check_occlusion(
                        scene, c, real_target, bone_name, f
                    ):
                        candidates.append(c)

                if candidates:
                    new_cam = random.choice(candidates)
                    recent = any(m.frame > f - 10 for m in scene.timeline_markers)
                    if not recent:
                        marker = scene.timeline_markers.new(f"Cut_{f}", frame=f)
                        marker.camera = new_cam
                        current_cam = new_cam

    @staticmethod
    def import_assets(directory, count=5):
        if not os.path.isdir(directory):
            return []
        subfolders = [f.path for f in os.scandir(directory) if f.is_dir()]

        if "Cinematic_Props" not in bpy.data.collections:
            props_col = bpy.data.collections.new("Cinematic_Props")
            bpy.context.scene.collection.children.link(props_col)
        else:
            props_col = bpy.data.collections["Cinematic_Props"]
            for o in props_col.objects:
                bpy.data.objects.remove(o, do_unlink=True)

        for i in range(count):
            try:
                if not subfolders:
                    break
                folder = random.choice(subfolders)
                blend = next(
                    (f for f in os.listdir(folder) if f.endswith(".blend")), None
                )
                if not blend:
                    continue
                with bpy.data.libraries.load(
                    os.path.join(folder, blend), link=False
                ) as (df, dt):
                    dt.objects = df.objects
                if not dt.objects:
                    continue

                holder = bpy.data.objects.new(f"Prop_{i}", None)
                props_col.objects.link(holder)

                angle = random.uniform(0, 6.28)
                dist = random.uniform(5, 18)
                holder.location = (math.cos(angle) * dist, math.sin(angle) * dist, 0)
                holder.rotation_euler.z = random.uniform(0, 6.28)

                for obj in dt.objects:
                    if obj:
                        props_col.objects.link(obj)
                        if not obj.parent:
                            obj.parent = holder
            except:
                pass


class CINEMATIC_OT_SetupEnv(bpy.types.Operator):
    bl_idname = "cinematic.setup_env"
    bl_label = "Generate Environment"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.cinematic_props

        # 1. Setup
        if props.skybox_path:
            CinematicUtils.setup_hdri_skybox(context, props.skybox_path)
        CinematicUtils.setup_scene_basics(context, use_ground=props.use_ground)
        context.scene.frame_start = 1
        context.scene.frame_end = props.animation_length

        # 2. Assets
        if props.assets_path:
            CinematicUtils.import_assets(props.assets_path, count=props.asset_count)

        self.report({"INFO"}, "Środowisko wygenerowane.")
        return {"FINISHED"}


class CINEMATIC_OT_SetupCameras(bpy.types.Operator):
    bl_idname = "cinematic.setup_cameras"
    bl_label = "Setup Cameras & Direct"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = context.scene.cinematic_props
        if not props.target_object:
            self.report({"ERROR"}, "Wybierz obiekt docelowy (Target)!")
            return {"CANCELLED"}

        # 3. Create Cameras
        cameras = CinematicUtils.setup_camera_system(
            context, props.target_object, radius=props.camera_distance
        )

        # 4. Director Logic
        if cameras:
            CinematicUtils.run_director_logic(
                context, cameras, props.target_object, 1, props.animation_length
            )
            self.report({"INFO"}, "Kamery ustawione.")
        else:
            self.report({"WARNING"}, "Plugin Multicam nie stworzył kamer!")

        return {"FINISHED"}


class CINEMATIC_PT_Director(bpy.types.Panel):
    bl_label = "Cinematic Director"
    bl_idname = "CINEMATIC_PT_Director"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Cinematic"

    def draw(self, context):
        layout = self.layout
        props = context.scene.cinematic_props
        layout.label(text="Input:", icon="IMPORT")
        layout.prop(props, "target_object")
        layout.prop(props, "assets_path", text="Assets Folder")
        layout.prop(props, "skybox_path", text="Skybox (.hdr)")
        layout.separator()
        layout.label(text="Parameters:", icon="PREFERENCES")
        layout.prop(props, "animation_length")
        layout.prop(props, "asset_count")
        layout.prop(props, "camera_distance")
        layout.prop(props, "use_ground", text="Create Ground")

        layout.separator()
        layout.label(text="Actions:", icon="PLAY")
        # DWA PRZYCISKI
        row = layout.row(align=True)
        row.operator("cinematic.setup_env", text="1. GENERATE SCENE", icon="WORLD")
        row = layout.row(align=True)
        row.operator(
            "cinematic.setup_cameras", text="2. SETUP CAMERAS", icon="CAMERA_DATA"
        )


class CinematicProperties(bpy.types.PropertyGroup):
    target_object: bpy.props.PointerProperty(
        type=bpy.types.Object, name="Target (SMPL Mesh)"
    )
    assets_path: bpy.props.StringProperty(name="Assets", subtype="DIR_PATH")
    skybox_path: bpy.props.StringProperty(name="Skybox", subtype="FILE_PATH")

    animation_length: bpy.props.IntProperty(name="Frames", default=250, min=10)
    asset_count: bpy.props.IntProperty(name="Asset Count", default=8, min=0)
    camera_distance: bpy.props.FloatProperty(name="Camera Dist", default=7.0, min=1.0)
    use_ground: bpy.props.BoolProperty(name="Use Ground", default=True)


classes = (
    CINEMATIC_PT_Director,
    CINEMATIC_OT_SetupEnv,
    CINEMATIC_OT_SetupCameras,
    CinematicProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cinematic_props = bpy.props.PointerProperty(
        type=CinematicProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.cinematic_props


if __name__ == "__main__":
    register()
