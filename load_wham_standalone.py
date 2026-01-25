import bpy
import json
import numpy as np
from mathutils import Vector, Matrix
import math

def animate_wham_with_camera(json_path, armature_name="smpl_armature", width=1920, height=1080, manual_fov_degrees=None):
    with open(json_path, 'r') as f:
        # There can be more than one animations stored, we take the first one.
        # Could also find character with longest screen time, like WHAM.
        data = json.load(f)["0"]

    arm = bpy.data.objects.get(armature_name)
    
    # This finds lowest vertex across whole animations and treats that height as Z=0
    # This way the animation looks like walking on grid, you can add a plane etc
    verts = np.array(data['verts'])
    min_y = verts[..., 1].min()

    p_world = np.array(data['pose_world'])
    t_world = np.array(data['trans_world'])
    p_local = np.array(data['pose'])
    t_local = np.array(data['trans'])
    
    smpl_bones = ["Pelvis", "L_Hip", "R_Hip", "Spine1", "L_Knee", "R_Knee", "Spine2", 
                  "L_Ankle", "R_Ankle", "Spine3", "L_Foot", "R_Foot", "Neck", "L_Collar", 
                  "R_Collar", "Head", "L_Shoulder", "R_Shoulder", "L_Elbow", "R_Elbow", 
                  "L_Wrist", "R_Wrist", "L_Hand", "R_Hand"]

    if "WHAM_Camera" in bpy.data.objects:
        cam_obj = bpy.data.objects["WHAM_Camera"]
    else:
        cam_data = bpy.data.cameras.new(name="WHAM_Camera_Data")
        cam_obj = bpy.data.objects.new("WHAM_Camera", cam_data)
        bpy.context.collection.objects.link(cam_obj)
    
    if manual_fov_degrees:
        cam_obj.data.lens_unit = 'FOV'
        cam_obj.data.angle = math.radians(manual_fov_degrees)
    else:
        focal_length = (width ** 2 + height ** 2) ** 0.5
        cam_obj.data.lens_unit = 'MILLIMETERS'
        sensor_width = 36.0
        cam_obj.data.lens = (focal_length / width) * sensor_width
        cam_obj.data.sensor_width = sensor_width
    cam_obj.data.shift_y = -0.1
    
    bpy.context.scene.render.resolution_x = int(width)
    bpy.context.scene.render.resolution_y = int(height)

    # the coordinate system transformations were created with claude code
    for f_idx in range(len(p_world)):
        fr = f_idx + 1
        
        # --- HUMAN POSITION (Grounded) ---
        p_world_vec = Vector((t_world[f_idx][0], t_world[f_idx][1] - min_y, t_world[f_idx][2]))
        
        p_bone = arm.pose.bones["Pelvis"]
        p_bone.location = p_world_vec
        p_bone.keyframe_insert(data_path="location", frame=fr)
        
        # --- HUMAN ROTATION ---
        for b_idx, bone_name in enumerate(smpl_bones):
            if bone_name in arm.pose.bones:
                pb = arm.pose.bones[bone_name]
                aa = p_world[f_idx][b_idx*3 : b_idx*3+3]
                mag = np.linalg.norm(aa)
                pb.rotation_mode = 'AXIS_ANGLE'
                pb.rotation_axis_angle = (mag, *(Vector(aa)/mag)) if mag > 1e-6 else (0,1,0,0)
                pb.keyframe_insert(data_path="rotation_axis_angle", frame=fr)
        
        # --- CAMERA POSITION & ROTATION ---
        # The relationship is:
        # point_camera = R_cam @ point_world + t_cam
        # where R_cam and t_cam define camera extrinsics
        
        # We know:
        # t_local = R_cam @ t_world + t_cam
        
        # For rotation, we use the pelvis rotations:
        # p_local = R_cam @ p_world
        
        tw = t_world[f_idx]
        tl = t_local[f_idx]
        
        pw_root = p_world[f_idx][0:3]
        pl_root = p_local[f_idx][0:3]
        
        # Convert axis-angle to rotation matrices
        def aa_to_matrix(aa):
            angle = np.linalg.norm(aa)
            if angle < 1e-6:
                return np.eye(3)
            axis = aa / angle
            K = np.array([[0, -axis[2], axis[1]],
                         [axis[2], 0, -axis[0]],
                         [-axis[1], axis[0], 0]])
            R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K
            return R
        
        R_world = aa_to_matrix(pw_root)
        R_local = aa_to_matrix(pl_root)
        
        # R_cam transforms world to camera
        R_cam = R_local @ R_world.T
        
        # t_cam is the translation in camera extrinsics
        t_cam = tl - R_cam @ tw
        
        # To get camera position in world coords, we need the inverse transform
        # If point_cam = R_cam @ point_world + t_cam
        # Then point_world = R_cam.T @ (point_cam - t_cam)
        # Camera is at origin in camera space, so point_cam = [0,0,0]
        # Camera_world_pos = R_cam.T @ (-t_cam) = -R_cam.T @ t_cam
        
        cam_pos_world = -R_cam.T @ t_cam
        cam_rot_world = R_cam.T
        
        # Now convert to Blender coordinates
        # WHAM world: X right, Y up, Z back
        # Blender world: X right, Y forward, Z up
        # Transformation: X_b = X_w, Y_b = -Z_w, Z_b = Y_w
        
        blender_from_wham = np.array([
            [1,  0,  0],   # X = X
            [0,  0, -1],   # Y = -Z
            [0,  1,  0]    # Z = Y
        ])
        
        # Camera rotation in world needs careful handling
        # In WHAM (CV): camera +Z = forward, +Y = down, +X = right
        # In Blender: world Z = up, camera looks down local -Z
        # Blender camera local: -Z = view direction, +Y = up in camera view
        
        # To match: rotate CV camera 90° around X to make Y point up
        # Then flip Z to make it point backward (Blender cameras look down -Z)
        cv_to_blender_cam = np.array([
            [ 1,  0,  0],   # X stays right
            [ 0,  0,  1],   # Y = Z (what was forward is now up)
            [ 0, -1,  0]    # Z = -Y (what was down is now back/view direction)
        ])
        
        cam_rot_world_blender_convention = cam_rot_world @ cv_to_blender_cam
        
        # Now convert to Blender world coordinates
        cam_pos_blender = blender_from_wham @ cam_pos_world
        cam_rot_blender = blender_from_wham @ cam_rot_world_blender_convention @ blender_from_wham.T
        
        # Apply ground offset
        cam_pos_blender[2] -= min_y
        
        # Create transformation matrix
        mat = Matrix.Identity(4)
        for i in range(3):
            for j in range(3):
                mat[i][j] = cam_rot_blender[i, j]
            mat[i][3] = cam_pos_blender[i]
        
        cam_obj.matrix_world = mat
        cam_obj.keyframe_insert(data_path="location", frame=fr)
        cam_obj.keyframe_insert(data_path="rotation_euler", frame=fr)
    
    bpy.context.scene.camera = cam_obj
    
    print(len(p_world), "frames")

animate_wham_with_camera(
    "/home/tomek/studia/mgr/sem2/TRAK/projekt/results/example/wham_output.json", 
    "SMPL-male",
    manual_fov_degrees=43,
    height=1920,
    width=1080
)
