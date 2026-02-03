#!/usr/bin/env python3
"""
RunPod Serverless Handler for ComfyUI Trellis 3D
Version 1.0.0

Features:
- Proper ComfyUI API integration (not subprocess)
- Non-blocking startup with pre-warming on first job
- Handles GLB, OBJ, images, and video outputs
- Robust error handling and logging
- Health checks and connectivity tests

Expected input formats:
1. Full workflow with embedded image:
   {"workflow": {...}, "image": "base64..."}

2. Workflow with separate files:
   {"workflow": {...}, "files": {"image": {"filename": "input.png", "data": "base64..."}}}

3. Test/health check:
   {} or {"test": true}
"""

import runpod
import requests
import json
import time
import base64
import os
import sys
from pathlib import Path
import uuid
import threading
import traceback

# ============================================================================
# CONFIGURATION
# ============================================================================

COMFYUI_URL = "http://localhost:8188"
COMFYUI_DIR = "/workspace/ComfyUI"
INPUT_DIR = Path(COMFYUI_DIR) / "input"
OUTPUT_DIR = Path(COMFYUI_DIR) / "output"
TEMP_DIR = Path(COMFYUI_DIR) / "temp"

# Supported output formats
OUTPUT_EXTENSIONS = {
    '3d': ('.glb', '.gltf', '.obj', '.stl', '.ply', '.fbx'),
    'image': ('.png', '.jpg', '.jpeg', '.webp', '.bmp'),
    'video': ('.mp4', '.webm', '.gif', '.mov'),
}

# Global state for pre-warming
_prewarm_attempted = False
_prewarm_success = False
_prewarm_lock = threading.Lock()


# ============================================================================
# LOGGING
# ============================================================================

def log(message: str, level: str = "INFO"):
    """Log with timestamp and level"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def log_separator(char: str = "=", length: int = 70):
    """Print a separator line"""
    print(char * length, flush=True)


# ============================================================================
# COMFYUI HEALTH & STARTUP
# ============================================================================

def wait_for_comfyui(timeout: int = 180):
    """Wait for ComfyUI to be ready"""
    log("Waiting for ComfyUI to start...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=5)
            if response.status_code == 200:
                elapsed = time.time() - start_time
                log(f"✅ ComfyUI is ready! (started in {elapsed:.1f}s)")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            log(f"Health check error: {e}", "WARN")
        time.sleep(2)
    
    raise TimeoutError(f"ComfyUI did not start within {timeout}s")


def get_system_info():
    """Get ComfyUI system information"""
    try:
        response = requests.get(f"{COMFYUI_URL}/system_stats", timeout=10)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None


# ============================================================================
# FILE HANDLING
# ============================================================================

def upload_file_to_comfyui(filename: str, file_data: str) -> str:
    """Upload base64-encoded file to ComfyUI input directory"""
    try:
        file_bytes = base64.b64decode(file_data)
        
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        file_path = INPUT_DIR / filename
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        log(f"Uploaded: {filename} ({len(file_bytes):,} bytes)")
        return str(file_path)
        
    except Exception as e:
        log(f"Error uploading {filename}: {e}", "ERROR")
        raise


def find_output_files(start_time: float = None) -> dict:
    """
    Find all output files from ComfyUI
    If start_time is provided, only return files modified after that time
    """
    outputs = {
        '3d': [],
        'image': [],
        'video': [],
        'other': []
    }
    
    search_dirs = [OUTPUT_DIR, TEMP_DIR]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
            
        for file_path in search_dir.rglob('*'):
            if not file_path.is_file():
                continue
            
            # Skip if file is older than job start
            if start_time and file_path.stat().st_mtime < start_time:
                continue
            
            ext = file_path.suffix.lower()
            
            # Categorize file
            categorized = False
            for category, extensions in OUTPUT_EXTENSIONS.items():
                if ext in extensions:
                    outputs[category].append(file_path)
                    categorized = True
                    break
            
            if not categorized and ext:
                outputs['other'].append(file_path)
    
    return outputs


def encode_file_to_base64(file_path: Path) -> dict:
    """Read file and encode to base64"""
    with open(file_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    
    return {
        'filename': file_path.name,
        'data': data,
        'size': file_path.stat().st_size,
        'type': file_path.suffix.lower().lstrip('.')
    }


# ============================================================================
# WORKFLOW HANDLING
# ============================================================================

def inject_image_into_workflow(workflow: dict, image_path: str) -> dict:
    """
    Inject image path into LoadImage nodes in the workflow
    Handles both API format and UI format workflows
    """
    workflow = workflow.copy()
    
    for node_id, node in workflow.items():
        if isinstance(node, dict):
            class_type = node.get('class_type', '')
            
            # Handle various image loading nodes
            if class_type in ('LoadImage', 'Load Image', 'ImageInput'):
                if 'inputs' in node:
                    node['inputs']['image'] = image_path
                else:
                    node['inputs'] = {'image': image_path}
                log(f"Injected image into node {node_id} ({class_type})")
    
    return workflow


def convert_ui_to_api(ui_workflow: dict) -> dict:
    """Convert UI workflow format to API format if needed"""
    # If it's already API format (has class_type at top level nodes)
    if not ("nodes" in ui_workflow and "links" in ui_workflow):
        return ui_workflow
    
    log("Converting UI workflow to API format...")
    
    nodes = ui_workflow.get("nodes", [])
    links = ui_workflow.get("links", [])
    api_workflow = {}
    
    # Build link lookup: link_id -> (source_node_id, source_slot)
    link_map = {}
    for link in links:
        if len(link) >= 4:
            link_id, source_node, source_slot, target_node, target_slot = link[:5]
            link_map[link_id] = (str(source_node), source_slot)
    
    for node in nodes:
        node_id = str(node["id"])
        node_data = {
            "inputs": {},
            "class_type": node["type"]
        }
        
        # Handle widget values
        if "widgets_values" in node:
            widget_values = node["widgets_values"]
            if isinstance(widget_values, dict):
                node_data["inputs"].update(widget_values)
        
        # Handle input connections
        for input_def in node.get("inputs", []):
            link_id = input_def.get("link")
            if link_id is not None and link_id in link_map:
                source_node_id, source_slot = link_map[link_id]
                node_data["inputs"][input_def["name"]] = [source_node_id, source_slot]
        
        api_workflow[node_id] = node_data
    
    return api_workflow


def queue_workflow(workflow: dict) -> tuple:
    """Queue workflow in ComfyUI and return (prompt_id, client_id)"""
    try:
        # Convert if needed
        api_workflow = convert_ui_to_api(workflow)
        
        client_id = str(uuid.uuid4())
        
        payload = {
            "prompt": api_workflow,
            "client_id": client_id
        }
        
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            error_text = response.text[:1000]
            log(f"Queue error response: {error_text}", "ERROR")
            raise Exception(f"Failed to queue workflow: {response.status_code}")
        
        result = response.json()
        prompt_id = result.get('prompt_id')
        
        if not prompt_id:
            raise Exception(f"No prompt_id in response: {result}")
        
        log(f"Queued workflow: {prompt_id}")
        return prompt_id, client_id
        
    except Exception as e:
        log(f"Error queueing workflow: {e}", "ERROR")
        raise


def wait_for_completion(prompt_id: str, timeout: int = 900) -> dict:
    """Wait for workflow to complete and return history"""
    log(f"Waiting for workflow {prompt_id}...")
    start_time = time.time()
    last_log_time = start_time
    
    while time.time() - start_time < timeout:
        try:
            # Check history for completion
            response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            history = response.json()
            
            if prompt_id in history:
                status = history[prompt_id].get('status', {})
                
                if status.get('completed'):
                    elapsed = time.time() - start_time
                    log(f"✅ Workflow completed in {elapsed:.1f}s")
                    return history[prompt_id]
                
                # Check for errors
                if status.get('status_str') == 'error':
                    error_msg = history[prompt_id].get('outputs', {})
                    raise Exception(f"Workflow failed: {error_msg}")
            
            # Progress logging every 15 seconds
            if time.time() - last_log_time >= 15:
                elapsed = int(time.time() - start_time)
                
                # Get queue status
                queue_response = requests.get(f"{COMFYUI_URL}/queue", timeout=10)
                queue = queue_response.json()
                running = len(queue.get('queue_running', []))
                pending = len(queue.get('queue_pending', []))
                
                log(f"Processing... ({elapsed}s elapsed, {running} running, {pending} pending)")
                last_log_time = time.time()
            
        except requests.exceptions.RequestException as e:
            log(f"Connection error: {e}", "WARN")
        
        time.sleep(2)
    
    raise TimeoutError(f"Workflow did not complete within {timeout}s")


def get_outputs_from_history(history: dict) -> dict:
    """Extract and encode output files from history"""
    outputs = {
        '3d': [],
        'image': [],
        'video': []
    }
    
    try:
        for node_id, node_output in history.get('outputs', {}).items():
            
            # Handle different output types
            for output_key in ['gltf', 'glb', 'mesh', '3d', 'model']:
                if output_key in node_output:
                    for item in node_output[output_key]:
                        file_info = _process_output_item(item, '3d')
                        if file_info:
                            outputs['3d'].append(file_info)
            
            if 'images' in node_output:
                for item in node_output['images']:
                    file_info = _process_output_item(item, 'image')
                    if file_info:
                        outputs['image'].append(file_info)
            
            if 'gifs' in node_output or 'videos' in node_output:
                for key in ['gifs', 'videos']:
                    for item in node_output.get(key, []):
                        file_info = _process_output_item(item, 'video')
                        if file_info:
                            outputs['video'].append(file_info)
    
    except Exception as e:
        log(f"Error parsing history outputs: {e}", "WARN")
    
    return outputs


def _process_output_item(item: dict, category: str) -> dict:
    """Process a single output item from history"""
    try:
        filename = item.get('filename')
        if not filename:
            return None
        
        subfolder = item.get('subfolder', '')
        file_type = item.get('type', 'output')
        
        if file_type == 'temp':
            base_dir = TEMP_DIR
        else:
            base_dir = OUTPUT_DIR
        
        if subfolder:
            file_path = base_dir / subfolder / filename
        else:
            file_path = base_dir / filename
        
        if file_path.exists():
            file_info = encode_file_to_base64(file_path)
            log(f"Encoded {category}: {filename} ({file_info['size']:,} bytes)")
            return file_info
        else:
            log(f"Output file not found: {file_path}", "WARN")
    
    except Exception as e:
        log(f"Error processing output item: {e}", "WARN")
    
    return None


# ============================================================================
# PRE-WARMING
# ============================================================================

def prewarm_models_if_needed():
    """Pre-warm notification on first job"""
    global _prewarm_attempted, _prewarm_success
    
    with _prewarm_lock:
        if _prewarm_attempted:
            return _prewarm_success
        
        _prewarm_attempted = True
        
        log_separator()
        log("🔥 FIRST JOB - Models will load on demand")
        log_separator()
        log("First generation takes 3-5 minutes (model loading)")
        log("Subsequent jobs will be faster")
        log_separator()
        
        _prewarm_success = True
        return True


# ============================================================================
# MAIN HANDLER
# ============================================================================

def handler(job):
    """
    RunPod serverless handler for Trellis 3D generation
    
    Input formats:
    1. {"workflow": {...}, "image": "base64..."}
    2. {"workflow": {...}, "files": {"image": {"filename": "x.png", "data": "base64..."}}}
    3. {"test": true} - connectivity test
    """
    job_id = job.get('id', str(uuid.uuid4())[:8])
    job_input = job.get('input', {})
    job_start_time = time.time()
    
    try:
        log_separator()
        log(f"📥 Job {job_id} started")
        log_separator()
        
        # Pre-warm notification on first job
        prewarm_models_if_needed()
        
        # -------------------------
        # Handle test/health check
        # -------------------------
        if not job_input or job_input.get('test'):
            sys_info = get_system_info()
            return {
                "status": "success",
                "message": "Handler ready for Trellis 3D generation",
                "test": True,
                "system": sys_info
            }
        
        # -------------------------
        # Get and validate workflow
        # -------------------------
        workflow = job_input.get('workflow')
        if not workflow:
            return {
                "status": "error",
                "error": "Missing 'workflow' in input"
            }
        
        # -------------------------
        # Handle image input
        # -------------------------
        image_path = None
        
        # Method 1: Direct base64 image
        if 'image' in job_input:
            filename = f"{job_id}_input.png"
            image_path = upload_file_to_comfyui(filename, job_input['image'])
        
        # Method 2: Files object
        elif 'files' in job_input:
            for file_key, file_info in job_input['files'].items():
                filename = file_info.get('filename', f"{job_id}_{file_key}")
                file_path = upload_file_to_comfyui(filename, file_info['data'])
                
                # Track image file
                if file_key == 'image' or filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    image_path = filename  # Use just filename for ComfyUI
        
        # -------------------------
        # Inject image into workflow
        # -------------------------
        if image_path:
            # Use just the filename for ComfyUI LoadImage node
            image_filename = Path(image_path).name
            workflow = inject_image_into_workflow(workflow, image_filename)
        
        # -------------------------
        # Queue and execute workflow
        # -------------------------
        prompt_id, client_id = queue_workflow(workflow)
        
        # Wait for completion (15 min timeout for 3D generation)
        history = wait_for_completion(prompt_id, timeout=900)
        
        # -------------------------
        # Collect outputs
        # -------------------------
        outputs = get_outputs_from_history(history)
        
        # Also scan for files created during this job
        file_outputs = find_output_files(start_time=job_start_time)
        
        # Merge and encode any additional files
        for category in ['3d', 'image', 'video']:
            existing_filenames = {o['filename'] for o in outputs[category]}
            for file_path in file_outputs.get(category, []):
                if file_path.name not in existing_filenames:
                    file_info = encode_file_to_base64(file_path)
                    outputs[category].append(file_info)
                    log(f"Found additional {category}: {file_path.name}")
        
        # -------------------------
        # Build response
        # -------------------------
        elapsed = time.time() - job_start_time
        
        response = {
            "status": "success",
            "prompt_id": prompt_id,
            "elapsed_seconds": round(elapsed, 1),
        }
        
        # Add 3D outputs (primary for Trellis)
        if outputs['3d']:
            response['glb'] = outputs['3d'][0]['data']  # Primary GLB
            response['3d_files'] = outputs['3d']
        
        # Add image outputs
        if outputs['image']:
            response['images'] = outputs['image']
        
        # Add video outputs
        if outputs['video']:
            response['videos'] = outputs['video']
        
        # Count totals
        total_outputs = len(outputs['3d']) + len(outputs['image']) + len(outputs['video'])
        
        log_separator()
        log(f"✅ Job {job_id} complete: {total_outputs} output(s) in {elapsed:.1f}s")
        log_separator()
        
        return response
        
    except Exception as e:
        elapsed = time.time() - job_start_time
        
        log_separator()
        log(f"❌ Job {job_id} failed after {elapsed:.1f}s: {str(e)}", "ERROR")
        log_separator()
        
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": round(elapsed, 1)
        }


# ============================================================================
# WORKER INITIALIZATION
# ============================================================================

if __name__ == "__main__":
    log_separator()
    log("🚀 RunPod Serverless Handler for Trellis 3D v1.0.0")
    log_separator()
    log(f"ComfyUI URL: {COMFYUI_URL}")
    log(f"ComfyUI Dir: {COMFYUI_DIR}")
    log(f"Input Dir: {INPUT_DIR}")
    log(f"Output Dir: {OUTPUT_DIR}")
    log_separator()
    
    # Wait for ComfyUI to be ready
    try:
        wait_for_comfyui(timeout=180)
    except Exception as e:
        log(f"FATAL: ComfyUI failed to start: {e}", "ERROR")
        sys.exit(1)
    
    log_separator()
    log("✅ HANDLER READY TO ACCEPT JOBS")
    log_separator()
    log("First job will take 3-5 min (model loading)")
    log("Subsequent jobs: ~1-3 min depending on settings")
    log_separator()
    
    # Start the handler - no blocking code after this
    runpod.serverless.start({"handler": handler})
