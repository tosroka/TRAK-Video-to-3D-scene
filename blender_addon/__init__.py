bl_info = {
    "name": "TRAK video to blender",
    "blender": (4, 4, 0),
    "category": "Object",
}
import bpy
from . import UI
from . import client
from . import processing
from .cameras import CINEMATIC_PT_Director, CINEMATIC_OT_SetupEnv, CINEMATIC_OT_SetupCameras, CinematicProperties

def poll_mesh_objects(self, object):
    return object.type == 'ARMATURE'

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
    bpy.utils.register_class(UI.MEDIA_OT_ProcessFiles)
    bpy.utils.register_class(UI.MEDIA_PT_MainPanel)
    bpy.utils.register_class(UI.MEDIA_PT_SettingsPanel)
    
    bpy.types.Scene.video_path = bpy.props.StringProperty(
        name="Video path",
        subtype='FILE_PATH'
    ) 

    bpy.types.Scene.image_path = bpy.props.StringProperty(
        name="Image Path",
        subtype='FILE_PATH'
    ) 

    bpy.types.Scene.target_object = bpy.props.PointerProperty(
        name="SMPL Model",
        type=bpy.types.Object,
        poll=poll_mesh_objects,
        description="Select a target SMPL model"
    )

    bpy.types.Scene.server_address = bpy.props.StringProperty(
        name="Server Address",
        description="IP or URL of the WHAM+SMPLitex server",
        default="http://localhost:5000"
    )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.cinematic_props

    bpy.utils.unregister_class(UI.MEDIA_OT_ProcessFiles)
    bpy.utils.unregister_class(UI.MEDIA_PT_MainPanel)
    bpy.utils.unregister_class(UI.MEDIA_PT_SettingsPanel)
    del bpy.types.Scene.video_path
    del bpy.types.Scene.image_path
    del bpy.types.Scene.target_object

if __name__ == "__main__":
    register()
