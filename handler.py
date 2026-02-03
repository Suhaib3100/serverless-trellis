import runpod
import subprocess
import json
import base64
import uuid
import os
import sys

COMFY_PATH = "/workspace/ComfyUI"
INPUT_DIR = "/workspace/input"
OUTPUT_DIR = "/workspace/output"

def inject_image_path(workflow, image_path):
    """
    Injects image path into any LoadImage node
    """
    for node_id, node in workflow.items():
        if node.get("class_type") == "LoadImage":
            node["inputs"]["image"] = image_path
    return workflow

def find_glb_file():
    for root, _, files in os.walk(OUTPUT_DIR):
        for f in files:
            if f.lower().endswith(".glb"):
                return os.path.join(root, f)
    return None

def handler(event):
    job_id = str(uuid.uuid4())

    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # -------------------------
    # Validate input
    # -------------------------
    if "input" not in event:
        return {"error": "Missing input"}

    payload = event["input"]

    if "image" not in payload or "workflow" not in payload:
        return {"error": "image and workflow required"}

    # -------------------------
    # Save input image
    # -------------------------
    image_path = f"{INPUT_DIR}/{job_id}.png"

    try:
        with open(image_path, "wb") as f:
            f.write(base64.b64decode(payload["image"]))
    except Exception as e:
        return {"error": f"Image decode failed: {str(e)}"}

    # -------------------------
    # Prepare workflow
    # -------------------------
    workflow = payload["workflow"]

    try:
        workflow = inject_image_path(workflow, image_path)
    except Exception as e:
        return {"error": f"Workflow injection failed: {str(e)}"}

    workflow_path = f"/workspace/{job_id}.json"

    with open(workflow_path, "w") as f:
        json.dump(workflow, f)

    # -------------------------
    # Run ComfyUI headless
    # -------------------------
    try:
        result = subprocess.run(
            [
                sys.executable,
                "main.py",
                "--workflow",
                workflow_path,
                "--output",
                OUTPUT_DIR
            ],
            cwd=COMFY_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        return {
            "error": "ComfyUI execution failed",
            "stdout": e.stdout[-4000:],
            "stderr": e.stderr[-4000:]
        }

    # -------------------------
    # Find GLB output
    # -------------------------
    glb_path = find_glb_file()

    if not glb_path or not os.path.exists(glb_path):
        return {"error": "GLB output not found"}

    # -------------------------
    # Return GLB as base64
    # -------------------------
    try:
        with open(glb_path, "rb") as f:
            glb_data = base64.b64encode(f.read()).decode()
    except Exception as e:
        return {"error": f"GLB read failed: {str(e)}"}

    return {
        "glb": glb_data
    }

runpod.serverless.start({
    "handler": handler
})
