import bpy
import math
import random
import os
from mathutils import Vector, Euler

bl_info = {
    "name": "Cinematic Director (Occlusion Fix)",
    "location": "View3D > Sidebar > Cinematic",
}

class CinematicUtils:
    @staticmethod
    def setup_scene_basics(context, use_ground=True):
        if use_ground and not bpy.data.objects.get("Cinematic_Ground"):
            bpy.ops.mesh.primitive_grid_add(size=200, location=(0,0,-0.05))
            ground = context.active_object
            ground.name = "Cinematic_Ground"
            ground.hide_select = True
            mat = bpy.data.materials.new("Ground_Mat")
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf: 
                bsdf.inputs['Base Color'].default_value = (0.05, 0.05, 0.05, 1)
                bsdf.inputs['Roughness'].default_value = 0.9
            ground.data.materials.append(mat)

    @staticmethod
    def setup_hdri_skybox(context, image_path):
        if not image_path or not os.path.exists(image_path): return
        world = context.scene.world
        if not world:
            world = bpy.data.worlds.new("CinematicWorld")
            context.scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()
        node_env = nodes.new(type='ShaderNodeTexEnvironment')
        node_env.location = (-300, 0)
        try:
            node_env.image = bpy.data.images.load(image_path)
        except: pass
        node_bg = nodes.new(type='ShaderNodeBackground')
        node_bg.location = (0, 0)
        node_out = nodes.new(type='ShaderNodeOutputWorld')
        node_out.location = (300, 0)
        links.new(node_env.outputs["Color"], node_bg.inputs["Color"])
        links.new(node_bg.outputs["Background"], node_out.inputs["Surface"])

    @staticmethod
    def aggressive_cleanup():
        to_delete = []
        for obj in bpy.data.objects:
            if "Master_Camera_Rig" in obj.name:
                to_delete.append(obj)
            if "Camera_O" in obj.name and obj.type == 'CAMERA':
                to_delete.append(obj)
                
        if to_delete:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in to_delete:
                obj.select_set(True)
            bpy.ops.object.delete()
                
        for cam_data in bpy.data.cameras:
            if cam_data.users == 0:
                bpy.data.cameras.remove(cam_data)

    @staticmethod
    def setup_camera_system(context, target_obj, radius=7.0):
        CinematicUtils.aggressive_cleanup()

        bpy.ops.object.camera_add(
            enter_editmode=False, 
            align='VIEW', 
            location=(0, 0, 0), 
            rotation=(1.01799, 6.77293e-07, 0.784868), 
            scale=(1, 1, 1)
        )
        
        rig = context.active_object
        rig.name = "Master_Camera_Rig"
        
        bpy.ops.object.select_all(action='DESELECT')
        rig.select_set(True)
        context.view_layer.objects.active = rig
        context.scene.camera = rig

        try:
            rig["camera_type"] = 'MESH'
            rig["pattern_type"] = 'ORBIT'
            rig["target_object"] = target_obj.name
            rig["radius"] = radius
            
            if hasattr(rig, "camera_type"): rig.camera_type = 'MESH'
            if hasattr(rig, "pattern_type"): rig.pattern_type = 'ORBIT'
            if hasattr(rig, "target_object"): rig.target_object = target_obj.name
            if hasattr(rig, "radius"): rig.radius = radius
            
        except Exception as e:
            print(f"Prop Warning: {e}")

        context.view_layer.update()

        try:
            if hasattr(bpy.ops.multicam, "set_mesh_cameras"):
                bpy.ops.multicam.set_mesh_cameras()
            else:
                print("ERROR: Multicam missing.")
                return []
        except Exception as e:
            print(f"Multicam Error: {e}")
            return []

        context.view_layer.update()

        const = rig.constraints.new(type='COPY_LOCATION')
        const.target = target_obj
        const.influence = 1.0 
        
        children_cameras = [child for child in rig.children if child.type == 'CAMERA']
        
        for cam in children_cameras:
            if cam.location.length > 0:
                cam.location = cam.location.normalized() * radius
            
            has_track = any(c.type == 'TRACK_TO' for c in cam.constraints)
            if not has_track:
                tt = cam.constraints.new(type='TRACK_TO')
                tt.target = target_obj
                tt.track_axis = 'TRACK_NEGATIVE_Z'
                tt.up_axis = 'UP_Y'

        print(f"Znaleziono {len(children_cameras)} kamer.")
        return children_cameras

    @staticmethod
    def check_occlusion(scene, camera, target_obj, frame_num):
        # 1. Pobieramy graf zależności dla AKTUALNEJ klatki
        depsgraph = bpy.context.evaluated_depsgraph_get()
        
        origin = camera.matrix_world.translation
        
        # 2. Inteligentny środek (60% wysokości obiektu)
        # Dzięki temu celujemy w klatkę piersiową/głowę, a nie w stopy (0,0,0)
        z_offset = target_obj.dimensions.z * 0.6
        if z_offset < 0.1: z_offset = 1.0 # Fallback
        
        target_center = target_obj.matrix_world.translation + Vector((0, 0, z_offset))
        
        direction = (target_center - origin).normalized()
        distance = (target_center - origin).length
        
        # 3. Raycast
        is_hit, hit_loc, hit_normal, hit_index, hit_obj, matrix = scene.ray_cast(
            depsgraph, origin, direction, distance=distance - 0.5
        )
        
        if is_hit:
            # Ignorujemy podłogę i sam cel
            if hit_obj.name == "Cinematic_Ground" or hit_obj == target_obj:
                return False
            
            # DEBUG: Pokaż co zasłania (Włącz konsolę: Window -> Toggle System Console)
            # print(f"[Frame {frame_num}] CAM: {camera.name} BLOCKED BY: {hit_obj.name}")
            return True 
            
        return False

    @staticmethod
    def run_director_logic(context, cameras, target_obj, start, end):
        scene = context.scene
        scene.timeline_markers.clear()
        if not cameras: return

        current_cam = cameras[0]
        m = scene.timeline_markers.new("Start", frame=start)
        m.camera = current_cam
        
        print(f"--- DIRECTOR START ({start}-{end}) ---")
        
        for f in range(start, end + 1):
            # 1. Ustaw klatkę
            scene.frame_set(f)
            
            # 2. WYMUŚ AKTUALIZACJĘ POZYCJI (To naprawia problem z kulą)
            context.view_layer.update()
            
            # Sprawdź czy obecna kamera jest zasłonięta
            is_occluded = CinematicUtils.check_occlusion(scene, current_cam, target_obj, f)
            
            if is_occluded:
                # Szukamy alternatywy
                candidates = []
                for c in cameras:
                    if c == current_cam: continue
                    # Jeśli kandydat ma czysty widok
                    if not CinematicUtils.check_occlusion(scene, c, target_obj, f):
                        candidates.append(c)
                
                if candidates:
                    new_cam = random.choice(candidates)
                    
                    # Cooldown (żeby nie mrugało co 1 klatkę)
                    recent = any(m.frame > f-5 for m in scene.timeline_markers)
                    
                    if not recent:
                        marker = scene.timeline_markers.new(f"Cut_{f}", frame=f)
                        marker.camera = new_cam
                        current_cam = new_cam
                        print(f"Frame {f}: CUT -> {new_cam.name} (Occlusion)")

    @staticmethod
    def import_assets(directory, count=5):
        if not os.path.isdir(directory): return []
        subfolders = [f.path for f in os.scandir(directory) if f.is_dir()]
        
        if "Cinematic_Props" not in bpy.data.collections:
            props_col = bpy.data.collections.new("Cinematic_Props")
            bpy.context.scene.collection.children.link(props_col)
        else:
            props_col = bpy.data.collections["Cinematic_Props"]
            for o in props_col.objects: bpy.data.objects.remove(o, do_unlink=True)

        for i in range(count):
            try:
                if not subfolders: break
                folder = random.choice(subfolders)
                blend = next((f for f in os.listdir(folder) if f.endswith(".blend")), None)
                if not blend: continue
                with bpy.data.libraries.load(os.path.join(folder, blend), link=False) as (df, dt):
                    dt.objects = df.objects
                if not dt.objects: continue
                
                holder = bpy.data.objects.new(f"Prop_{i}", None)
                props_col.objects.link(holder)
                
                angle = random.uniform(0, 6.28)
                dist = random.uniform(5, 18)
                holder.location = (math.cos(angle)*dist, math.sin(angle)*dist, 0)
                holder.rotation_euler.z = random.uniform(0, 6.28)
                
                for obj in dt.objects:
                    if obj:
                        props_col.objects.link(obj)
                        if not obj.parent: obj.parent = holder
            except: pass

# --- PANEL ---
class CINEMATIC_PT_Director(bpy.types.Panel):
    bl_label = "Cinematic Director"
    bl_idname = "CINEMATIC_PT_Director"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Cinematic'

    def draw(self, context):
        layout = self.layout
        props = context.scene.cinematic_props
        layout.label(text="Input:", icon='IMPORT')
        layout.prop(props, "target_object")
        layout.prop(props, "assets_path", text="Assets Folder")
        layout.prop(props, "skybox_path", text="Skybox (.hdr)")
        layout.separator()
        layout.label(text="Parameters:", icon='PREFERENCES')
        layout.prop(props, "animation_length")
        layout.prop(props, "asset_count")
        layout.prop(props, "camera_distance")
        layout.prop(props, "use_ground", text="Create Ground")
        layout.separator()
        layout.operator("cinematic.run_director", text="GENERUJ SCENĘ", icon='RENDER_ANIMATION')

class CINEMATIC_OT_RunDirector(bpy.types.Operator):
    bl_idname = "cinematic.run_director"
    bl_label = "Generate Scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.cinematic_props
        if not props.target_object: return {'CANCELLED'}

        # 1. Setup
        if props.skybox_path: CinematicUtils.setup_hdri_skybox(context, props.skybox_path)
        CinematicUtils.setup_scene_basics(context, use_ground=props.use_ground)
        context.scene.frame_start = 1
        context.scene.frame_end = props.animation_length
        
        # 2. Assets
        if props.assets_path:
            CinematicUtils.import_assets(props.assets_path, count=props.asset_count)

        # 3. Create Cameras
        cameras = CinematicUtils.setup_camera_system(context, props.target_object, radius=props.camera_distance)

        # 4. Director Logic
        if cameras:
            CinematicUtils.run_director_logic(
                context, cameras, props.target_object, 
                1, props.animation_length
            )
        else:
            self.report({'WARNING'}, "Plugin Multicam nie stworzył kamer-dzieci!")

        return {'FINISHED'}

class CinematicProperties(bpy.types.PropertyGroup):
    target_object: bpy.props.PointerProperty(type=bpy.types.Object, name="Target (SMPL)")
    assets_path: bpy.props.StringProperty(name="Assets", subtype='DIR_PATH')
    skybox_path: bpy.props.StringProperty(name="Skybox", subtype='FILE_PATH')
    
    animation_length: bpy.props.IntProperty(name="Frames", default=250, min=10)
    asset_count: bpy.props.IntProperty(name="Asset Count", default=8, min=0)
    camera_distance: bpy.props.FloatProperty(name="Camera Dist", default=7.0, min=1.0)
    use_ground: bpy.props.BoolProperty(name="Use Ground", default=True)

def register():
    bpy.utils.register_class(CINEMATIC_PT_Director)
    bpy.utils.register_class(CINEMATIC_OT_RunDirector)
    bpy.utils.register_class(CinematicProperties)
    bpy.types.Scene.cinematic_props = bpy.props.PointerProperty(type=CinematicProperties)

def unregister():
    bpy.utils.unregister_class(CINEMATIC_PT_Director)
    bpy.utils.unregister_class(CINEMATIC_OT_RunDirector)
    bpy.utils.unregister_class(CinematicProperties)
    del bpy.types.Scene.cinematic_props

if __name__ == "__main__":
    register() 