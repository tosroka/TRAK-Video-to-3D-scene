import bpy
from . import client

class MEDIA_OT_ProcessFiles(bpy.types.Operator):
    bl_label = "Extract model from video"
    bl_idname = "addon.process_files"

    def execute(self, context):
        scene = context.scene
        client.run(scene.video_path, scene.image_path, scene.server_address)
        return {'FINISHED'}
    
class MEDIA_PT_MainPanel(bpy.types.Panel):
    bl_label = "Video to SMPL"
    bl_idname = "MEDIA_PT_MainPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TRAK'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "target_object")

        layout.label(text="Select Files:")
        layout.prop(scene, "video_path")
        layout.prop(scene, "image_path")
        
        
        layout.separator()
        layout.operator("addon.process_files", icon='PLAY')

class MEDIA_PT_SettingsPanel(bpy.types.Panel):
    bl_label = "Settings"
    bl_idname = "MEDIA_PT_SettingsPanel"
    bl_parent_id = "MEDIA_PT_MainPanel" 
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene, "server_address", icon='URL')
