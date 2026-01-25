import requests
import time
import os

# Configuration
URL = "http://127.0.0.1:5000"
VIDEO_PATH = "example.mp4"
IMAGE_PATH = "example.png"
SAVE_DIR = "./client_downloads"

def run_test():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    with open(VIDEO_PATH, 'rb') as f, open(IMAGE_PATH, 'rb') as fi:
        files = {'video': f, 'image': fi}
        response = requests.post(f"{URL}/process", files=files)
    
    if response.status_code != 200:
        print("Failed to start processing.")
        return

    job_id = response.json().get('job_id')
    print(f"Started job: {job_id}")

    while True:
        status_resp = requests.get(f"{URL}/status/{job_id}")
        status = status_resp.json().get('status')
        print(f"Current Status: {status}")

        if status == 'COMPLETED':
            print("Pipeline finished! Downloading results...")
            break
        elif 'ERROR' in status:
            print(f"Something went wrong: {status}")
            return
        
        time.sleep(2)

    for file_type in ['motion', 'texture']:
        file_resp = requests.get(f"{URL}/download/{job_id}/{file_type}")
        ext = ".json" if file_type == 'motion' else ".png"
        save_path = os.path.join(SAVE_DIR, f"{job_id}_{file_type}{ext}")
        
        with open(save_path, 'wb') as f:
            f.write(file_resp.content)
        print(f"Saved: {save_path}")

if __name__ == "__main__":
    run_test()
