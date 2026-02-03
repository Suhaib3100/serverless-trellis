#!/usr/bin/env python3
"""
Test the RunPod handler locally on the pod.
Simulates what RunPod serverless would send.
"""
import json
import base64
import sys
import os

# Add ComfyUI to path
sys.path.insert(0, '/workspace/trellis-test/ComfyUI')

# Load workflow
with open('/workspace/test/workflow.json', 'r') as f:
    workflow = json.load(f)

# Load and encode image
with open('/workspace/test/fan.png', 'rb') as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

print(f"Loaded workflow with {len(workflow)} nodes")
print(f"Loaded image: {len(image_b64)} bytes (base64)")

# Create fake job input (like RunPod would send)
job = {
    "id": "test-job-001",
    "input": {
        "workflow": workflow,
        "image": image_b64
    }
}

print("\n" + "="*60)
print("Starting handler test...")
print("="*60 + "\n")

# Import and run handler
from handler import handler

result = handler(job)

print("\n" + "="*60)
print("RESULT:")
print("="*60)
print(json.dumps({k: v if k != 'glb' else f'<{len(v)} bytes>' for k, v in result.items()}, indent=2))

# Save GLB if present
if result.get('status') == 'success' and result.get('glb'):
    glb_data = base64.b64decode(result['glb'])
    output_path = '/workspace/test/output.glb'
    with open(output_path, 'wb') as f:
        f.write(glb_data)
    print(f"\n✅ GLB saved to: {output_path} ({len(glb_data):,} bytes)")
