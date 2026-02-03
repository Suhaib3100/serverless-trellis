#!/bin/bash
set -e

echo "=============================="
echo "Trellis ComfyUI Test Setup"
echo "=============================="

# ---- HF TOKEN (optional for full models) ----
HF_TOKEN="${HF_TOKEN:-}"
if [ -z "$HF_TOKEN" ]; then
  echo "⚠️  HF_TOKEN not set - will skip gated models (Trellis, RMBG, DINOv3)"
  echo "   Set with: export HF_TOKEN=your_token"
fi

# ---- BASIC CHECKS ----
echo "[1/12] Checking GPU"
nvidia-smi || echo "nvidia-smi not found, continuing anyway..."

python3 - <<EOF
import torch
print("CUDA available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM:", round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1), "GB")
EOF

# ---- WORKSPACE ----
echo "[2/12] Creating workspace"
cd /workspace
mkdir -p trellis-test
cd trellis-test

# ---- COMFYUI ----
echo "[3/12] Cloning ComfyUI"
if [ ! -d "ComfyUI" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git
fi
cd ComfyUI

# ---- PYTHON DEPS ----
echo "[4/12] Installing core requirements"
pip install --upgrade pip
pip install -r requirements.txt
pip install runpod  # For serverless handler

# ---- GPU / 3D STACK ----
echo "[5/12] Installing GPU + 3D dependencies"
pip install spconv-cu120 || echo "spconv install failed, continuing..."
pip install kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.4.1_cu121.html || echo "kaolin install failed, continuing..."
pip install git+https://github.com/facebookresearch/pytorch3d.git || echo "pytorch3d install failed, continuing..."
pip install trimesh pymcubes pymeshlab rembg opencv-python scipy moviepy meshlib requests

# ---- CUSTOM NODES ----
echo "[6/12] Installing custom nodes"
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

echo "[7/12] Installing node requirements"
for d in */requirements.txt; do pip install -r "$d" || true; done

# ---- MODEL DIRECTORIES ----
echo "[8/12] Creating model directories"
cd /workspace/trellis-test/ComfyUI
mkdir -p models/trellis2/ckpts
mkdir -p models/UltraShape
mkdir -p models/BiRefNet/RMBG-2.0
mkdir -p models/facebook/dinov3-vitl16-pretrain-lvd1689m

# ---- ULTRASHAPE (public) ----
echo "[9/12] Downloading UltraShape model"
cd models/UltraShape
if [ ! -f ultrashape_v1.pt ]; then
  wget -q --show-progress https://huggingface.co/Rizzlord/UltraShape/resolve/main/ultrashape_v1.pt
fi

# ---- TRELLIS + RMBG + DINO (needs HF_TOKEN) ----
if [ -n "$HF_TOKEN" ]; then
  echo "[10/12] Downloading Trellis 2 models..."
  cd /workspace/trellis-test/ComfyUI/models/trellis2/ckpts
  
  # Core Trellis 2 checkpoints
  for f in \
    ss_dec_conv3d_16l8_fp16 \
    ss_flow_img_dit_1_3B_64_bf16 \
    shape_dec_next_dc_f16c32_fp16 \
    slat_flow_img2shape_dit_1_3B_512_bf16 \
    tex_dec_next_dc_f16c32_fp16 \
    slat_flow_imgshape2tex_dit_1_3B_512_bf16; do
    
    if [ ! -f "${f}.safetensors" ]; then
      echo "  Downloading $f..."
      curl -sL -H "Authorization: Bearer $HF_TOKEN" \
        -o "${f}.safetensors" \
        "https://huggingface.co/microsoft/TRELLIS.2-4B/resolve/main/ckpts/${f}.safetensors" || true
      curl -sL -H "Authorization: Bearer $HF_TOKEN" \
        -o "${f}.json" \
        "https://huggingface.co/microsoft/TRELLIS.2-4B/resolve/main/ckpts/${f}.json" || true
    fi
  done
  
  # RMBG model
  echo "[11/12] Downloading RMBG model..."
  cd /workspace/trellis-test/ComfyUI/models/BiRefNet/RMBG-2.0
  if [ ! -f model.safetensors ]; then
    curl -sL -H "Authorization: Bearer $HF_TOKEN" -o model.safetensors \
      https://huggingface.co/briaai/RMBG-2.0/resolve/main/model.safetensors || true
    curl -sL -H "Authorization: Bearer $HF_TOKEN" -o config.json \
      https://huggingface.co/briaai/RMBG-2.0/resolve/main/config.json || true
  fi
  
  # DINOv3 model
  echo "Downloading DINOv3 model..."
  cd /workspace/trellis-test/ComfyUI/models/facebook/dinov3-vitl16-pretrain-lvd1689m
  if [ ! -f model.safetensors ]; then
    curl -sL -H "Authorization: Bearer $HF_TOKEN" -o model.safetensors \
      https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m/resolve/main/model.safetensors || true
    curl -sL -H "Authorization: Bearer $HF_TOKEN" -o config.json \
      https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m/resolve/main/config.json || true
  fi
else
  echo "[10/12] Skipping Trellis models (no HF_TOKEN)"
  echo "[11/12] Skipping RMBG/DINOv3 models (no HF_TOKEN)"
fi

# ---- COPY HANDLER ----
echo "[12/12] Setting up handler"
cd /workspace/trellis-test/ComfyUI
# Handler should be copied separately via SCP

# ---- DONE ----
echo ""
echo "=============================="
echo "✅ SETUP COMPLETE"
echo "=============================="
echo ""
echo "To run ComfyUI manually:"
echo "  cd /workspace/trellis-test/ComfyUI"
echo "  python3 main.py --listen 0.0.0.0 --port 8188"
echo ""
echo "To test the handler:"
echo "  cd /workspace/trellis-test/ComfyUI"
echo "  python3 handler.py"
echo ""
echo "Access ComfyUI at: http://your-pod-ip:8188"
echo "=============================="
