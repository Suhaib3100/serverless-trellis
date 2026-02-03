#!/bin/bash
set -e

echo "=============================="
echo "Trellis ComfyUI Test Setup"
echo "=============================="

# ---- BASIC CHECKS ----
echo "[1/10] Checking GPU"
nvidia-smi

python3 - <<EOF
import torch
print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0))
EOF

# ---- WORKSPACE ----
echo "[2/10] Creating workspace"
cd ~
mkdir -p trellis-test
cd trellis-test

# ---- COMFYUI ----
echo "[3/10] Cloning ComfyUI"
if [ ! -d "ComfyUI" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git
fi
cd ComfyUI

# ---- PYTHON DEPS ----
echo "[4/10] Installing core requirements"
pip install --upgrade pip
pip install -r requirements.txt

# ---- GPU / 3D STACK ----
echo "[5/10] Installing GPU + 3D dependencies"
pip install spconv-cu120
pip install kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.4.1_cu121.html
pip install git+https://github.com/facebookresearch/pytorch3d.git
pip install trimesh pymcubes pymeshlab rembg opencv-python scipy moviepy meshlib requests

# ---- CUSTOM NODES ----
echo "[6/10] Installing custom nodes"
cd custom_nodes

clone() {
  if [ ! -d "$2" ]; then
    git clone "$1" "$2"
  fi
}

clone https://github.com/visualbruno/ComfyUI-Trellis2.git ComfyUI-Trellis2
clone https://github.com/jtydhr88/ComfyUI-UltraShape1.git ComfyUI-UltraShape1
clone https://github.com/1038lab/ComfyUI-RMBG.git ComfyUI-RMBG
clone https://github.com/rgthree/rgthree-comfy.git rgthree-comfy
clone https://github.com/LAOGOU-666/Comfyui-Memory_Cleanup.git Comfyui-Memory_Cleanup
clone https://github.com/PozzettiAndrea/ComfyUI-GeometryPack.git ComfyUI-GeometryPack
clone https://github.com/MrForExample/ComfyUI-3D-Pack.git ComfyUI-3D-Pack

echo "[7/10] Installing node requirements"
for d in */requirements.txt; do pip install -r "$d" || true; done

# ---- MODELS (MINIMAL TEST) ----
echo "[8/10] Creating model directories"
cd ~/trellis-test/ComfyUI
mkdir -p models/UltraShape

echo "[9/10] Downloading ONE test model (UltraShape)"
cd models/UltraShape
if [ ! -f ultrashape_v1.pt ]; then
  wget https://huggingface.co/Rizzlord/UltraShape/resolve/main/ultrashape_v1.pt
fi

# ---- DONE ----
echo "[10/10] DONE"
echo "--------------------------------"
echo "Run ComfyUI with:"
echo "cd ~/trellis-test/ComfyUI"
echo "python3 main.py --listen 0.0.0.0 --port 8188"
echo "--------------------------------"
