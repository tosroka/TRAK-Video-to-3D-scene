# Video to Blender scene

Blender addon that extracts movement and texture from video, then loads it into a blender project.

The addon is a client that connects to flask server, which in turn calls local WHAM and SMPLitex installations. Provide correct paths in `config.py`

Project structure:
```
.
├── app.py
├── blender_addon
│   ├── client.py - connects to server and receives motion+texture
│   ├── __init__.py
│   ├── processing.py - loads results into blender project
│   └── UI.py - addon UI in toolbar (N key)
├── config.py - modify this file with correct WHAM and SMPLitex installation paths!!!
├── example.mp4
├── example.png
├── load_wham_standalone.py - can be used as a script in Blender
├── projekt.blend - example scene
├── README.md
├── requirements.txt - requirements for flask server (needs joblib and torch to convert WHAM results)
├── test_client.py - same as addon client, but outside of blender
```
