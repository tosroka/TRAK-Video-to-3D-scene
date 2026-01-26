import os
import subprocess
import threading
from flask import Flask, request, jsonify, send_file
import config
from enum import Enum
from dataclasses import dataclass
from pathlib import Path
import joblib
import json
env = os.environ.copy()

app = Flask(__name__)

class JobStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    QUEUED = "QUEUED"
    WHAM_RUNNING = "WHAM_RUNNING"
    SMPLITEX_RUNNING = "SMPLITEX_RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"

@dataclass
class Job():
    status : JobStatus
    files : dict[str, Path]
    error : str

JOBS : dict[str, Job] = {} 


def run_pipeline(job_id: str, video_path: Path, image_path: Path):
    smpltex_data = image_path.parent.parent
    try:
        JOBS[job_id].status = JobStatus.WHAM_RUNNING
        
        subprocess.run([config.WHAM_PYTHON, "demo.py", "--video", video_path.absolute(), "--output_pth", Path("results").absolute(), "--save_pkl"], check=True, cwd=config.WHAM_WORKING_DIR)
        
        JOBS[job_id].status = JobStatus.SMPLITEX_RUNNING

        # smplitex has the worst code ever and calls system("python ...") so we must actually fake out the python executable.
        # Place path to conda env BEFORE real path, so it has priority

        smplitex_env = config.SMPLITEX_PYTHON.parent.parent
        if os.name == 'nt':
            # wasn't tested
            env["PATH"] = f"{smplitex_env};{smplitex_env}/Scripts;{smplitex_env}/Library/bin;" + env["PATH"]
        else:
            env["PATH"] = f"{smplitex_env}/bin:" + env["PATH"]

        # detectron, takes IMAGES path to waste some debugging time
        subprocess.run([config.SMPLITEX_PYTHON, "image_to_densepose.py", "--detectron2", "../detectron2", "--input_folder", (smpltex_data/"images").absolute()], check=True, cwd=config.SMPLITEX_WORKING_DIR/"scripts", env=env)
        
        # silhouette
        print("searching for images at",(smpltex_data/"images").absolute())
        subprocess.run([config.SMPLITEX_PYTHON, "SemanticGuidedHumanMatting/test_image.py", "--images-dir", (smpltex_data/"images").absolute(), "--result-dir", (smpltex_data/"images-seg").absolute(), "--pretrained-weight", "SemanticGuidedHumanMatting/pretrained/SGHM-ResNet50.pth"], check=True, cwd=config.SMPLITEX_WORKING_DIR/"scripts", env=env)
        
        # get texturemap. This takes root folder!!!
        print("final step")
        subprocess.run([config.SMPLITEX_PYTHON, "compute_partial_texturemap.py", "--input_folder", smpltex_data.absolute()], check=True, cwd=config.SMPLITEX_WORKING_DIR/"scripts", env=env)
        

        # start SD
        proc = subprocess.Popen(
             ["bash", "webui.sh"],
             stdout=subprocess.PIPE,
             stderr=subprocess.STDOUT,
             text=True,
             bufsize=1,
             cwd=config.STABLE_DIFFUSION,
             env=env
         )

        for line in proc.stdout:
             print(f"[WebUI]: {line}", end="")
             if "Model loaded" in line:
                 break

        # run img2img with stable diffusion
        print("img 2 img")
        subprocess.run([config.SMPLITEX_PYTHON, "inpaint_with_A1111.py", "--partial_textures", (smpltex_data/"uv-textures").absolute(), "--masks", (smpltex_data/"uv-textures-masks").absolute(), "--inpainted_textures", (Path("results") / image_path.stem).absolute()], check=True, cwd=config.SMPLITEX_WORKING_DIR/"scripts", env=env)

        # blender has no joblib, so convert it to json beforehand!
        data = joblib.load(Path("results") / video_path.stem / "wham_output.pkl")

        # rebuild data because it has int64 keys and ndarrays
        data_new = {int(x) : {k : data[x][k].tolist() for k in data[x]} for x in data}

        # save it to file for good measure
        with (Path("results") / video_path.stem / "wham_output.json").open("w") as f:
            json.dump(data_new, f)

        JOBS[job_id].status = JobStatus.COMPLETED
        JOBS[job_id].files = {
            "motion": Path("results") / video_path.stem / "wham_output.json",
            "texture": list((Path("results") / image_path.stem).glob("*.png"))[0]
        }
    except Exception as e:
        JOBS[job_id].status = JobStatus.ERROR
        JOBS[job_id].error = f"{str(e)}"

@app.route('/process', methods=['POST'])
def process_video():
    video = request.files['video']
    if not video.filename:
        return jsonify({"error": "video needs a filename"})
    path = Path("uploads")/"videos"/video.filename
    video.save(path)

    image = request.files['image']
    if not image.filename:
        return jsonify({"error": "image needs a filename"})
    # SMPLitex needs a subfolder...
    image_folder = Path("uploads")
    image_folder.mkdir(exist_ok=True)
    # save as jpg because SMPLitex is incredibly dumb
    image_final_path = (image_folder/"images"/image.filename).with_suffix(".jpg")
    image.save(image_final_path)    

    job_id = "job_" + str(len(JOBS))
    JOBS[job_id] = Job(status= JobStatus.QUEUED, files = {}, error = "")
    thread = threading.Thread(target=run_pipeline, args=(job_id, path, image_final_path))
    thread.start()
    
    return jsonify({"job_id": job_id})

@app.route('/status/<job_id>')
def get_status(job_id):
    if job_id in JOBS:
        resp = JOBS[job_id].status
        if JOBS[job_id].error:
            resp+=", "+JOBS[job_id].error
    else:
        resp = "Job is not started"
    return jsonify({"status": resp})

@app.route('/download/<job_id>/<file_type>')
def download(job_id, file_type):
    job = JOBS.get(job_id)
    if job and job.status == JobStatus.COMPLETED:
        return send_file(job.files[file_type])
    return "Not ready", 404

if __name__ == '__main__':
    Path("results").mkdir(exist_ok=True)
    Path("uploads/videos").mkdir(exist_ok=True, parents=True)
    Path("uploads/images").mkdir(exist_ok=True, parents=True)
    app.run(port=5000)
