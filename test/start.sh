#!/bin/bash
set -e

# =========================
# CONFIG
# =========================
BASE_DIR="/workspace"
COMFY_DIR="$BASE_DIR/ComfyUI"
VENV_DIR="$COMFY_DIR/venv"
MODELS_DIR="$COMFY_DIR/models/trellis2/ckpts"

echo "========================================="
echo " ComfyUI + TRELLIS2 FULL INSTALL SCRIPT"
echo "========================================="

# =========================
# SYSTEM DEPENDENCIES
# =========================
sudo apt update
sudo apt install -y \
  git wget curl unzip \
  python3 python3-venv python3-pip \
  ffmpeg libgl1 libglib2.0-0

# =========================
# CLEAN OLD INSTALL
# =========================
rm -rf "$COMFY_DIR"
mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

# =========================
# CLONE COMFYUI
# =========================
git clone https://github.com/comfyanonymous/ComfyUI.git
cd "$COMFY_DIR"

# =========================
# PYTHON VENV
# =========================
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# =========================
# INSTALL COMFYUI MANAGER
# =========================
cd custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git

# =========================
# INSTALL TRELLIS2 NODES
# =========================
git clone https://github.com/PozzettiAndrea/ComfyUI-TRELLIS2.git
cd ComfyUI-TRELLIS2
pip install -r requirements.txt
python install.py

# =========================
# MODEL DIRECTORIES
# =========================
mkdir -p "$MODELS_DIR"
cd "$MODELS_DIR"

# =========================
# TRELLIS IMAGE LARGE
# =========================
wget -c https://huggingface.co/microsoft/TRELLIS-image-large/resolve/main/ckpts/ss_dec_conv3d_16l8_fp16.json
wget -c https://huggingface.co/microsoft/TRELLIS-image-large/resolve/main/ckpts/ss_dec_conv3d_16l8_fp16.safetensors

# =========================
# TRELLIS 2-4B MODELS
# =========================
BASE_URL="https://huggingface.co/microsoft/TRELLIS.2-4B/resolve/main/ckpts"

FILES=(
  ss_flow_img_dit_1_3B_64_bf16
  shape_enc_next_dc_f16c32_fp16
  shape_dec_next_dc_f16c32_fp16
  slat_flow_img2shape_dit_1_3B_512_bf16
  slat_flow_img2shape_dit_1_3B_1024_bf16
  slat_flow_imgshape2tex_dit_1_3B_512_bf16
  slat_flow_imgshape2tex_dit_1_3B_1024_bf16
  tex_enc_next_dc_f16c32_fp16
  tex_dec_next_dc_f16c32_fp16
)

for f in "${FILES[@]}"; do
  wget -c "$BASE_URL/$f.json"
  wget -c "$BASE_URL/$f.safetensors"
done

# =========================
# DONE
# =========================
echo ""
echo "========================================="
echo " INSTALL COMPLETE"
echo "========================================="
echo ""
echo "Next step:"
echo "cd /workspace/ComfyUI"
echo "source venv/bin/activate"
echo "python main.py --listen 0.0.0.0 --port 8188"
echo ""