FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV FORCE_CUDA=1
ENV TORCH_CUDA_ARCH_LIST="8.0 8.6 8.9"

# -------------------------
# System dependencies
# -------------------------
RUN apt update && apt install -y \
    git python3 python3-pip curl wget \
    libgl1 libglib2.0-0 libsndfile1 ffmpeg \
    build-essential ninja-build \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# -------------------------
# PyTorch CUDA 12.1
# -------------------------
RUN pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu121

# -------------------------
# ComfyUI
# -------------------------
WORKDIR /workspace
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

WORKDIR /workspace/ComfyUI
RUN pip install -r requirements.txt

# -------------------------
# GPU / 3D dependencies
# -------------------------
RUN pip install spconv-cu120
RUN pip install kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.4.1_cu121.html
RUN pip install git+https://github.com/facebookresearch/pytorch3d.git
RUN pip install moviepy rembg Trimesh PyMCubes meshlib pymeshlab opencv-python scipy requests

# Optional speedups (non-fatal)
RUN pip install flash-attn --no-build-isolation || true
RUN pip install cubvh --no-build-isolation || true

# -------------------------
# Custom nodes
# -------------------------
WORKDIR /workspace/ComfyUI/custom_nodes

RUN git clone https://github.com/visualbruno/ComfyUI-Trellis2.git
RUN git clone https://github.com/jtydhr88/ComfyUI-UltraShape1.git
RUN git clone https://github.com/1038lab/ComfyUI-RMBG.git
RUN git clone https://github.com/rgthree/rgthree-comfy.git
RUN git clone https://github.com/LAOGOU-666/Comfyui-Memory_Cleanup.git
RUN git clone https://github.com/PozzettiAndrea/ComfyUI-GeometryPack.git
RUN git clone https://github.com/MrForExample/ComfyUI-3D-Pack.git

RUN for d in */requirements.txt; do pip install -r $d || true; done

# -------------------------
# Models
# -------------------------
ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}

WORKDIR /workspace/ComfyUI/models

RUN mkdir -p \
    trellis2/ckpts \
    UltraShape \
    BiRefNet/RMBG-2.0 \
    facebook/dinov3-vitl16-pretrain-lvd1689m

# ---- Trellis 2 ----
RUN curl -L -H "Authorization: Bearer $HF_TOKEN" \
    -o trellis2/ckpts/ss_dec_conv3d_16l8_fp16.safetensors \
    https://huggingface.co/microsoft/TRELLIS-image-large/resolve/main/ckpts/ss_dec_conv3d_16l8_fp16.safetensors && \
    curl -L -H "Authorization: Bearer $HF_TOKEN" \
    -o trellis2/ckpts/ss_dec_conv3d_16l8_fp16.json \
    https://huggingface.co/microsoft/TRELLIS-image-large/resolve/main/ckpts/ss_dec_conv3d_16l8_fp16.json

RUN for f in \
    ss_flow_img_dit_1_3B_64_bf16 \
    shape_dec_next_dc_f16c32_fp16 \
    slat_flow_img2shape_dit_1_3B_512_bf16 \
    slat_flow_img2shape_dit_1_3B_1024_bf16 \
    tex_dec_next_dc_f16c32_fp16 \
    slat_flow_imgshape2tex_dit_1_3B_512_bf16 \
    slat_flow_imgshape2tex_dit_1_3B_1024_bf16; do \
    curl -L -H "Authorization: Bearer $HF_TOKEN" \
      -o trellis2/ckpts/$f.safetensors \
      https://huggingface.co/microsoft/TRELLIS.2-4B/resolve/main/ckpts/$f.safetensors && \
    curl -L -H "Authorization: Bearer $HF_TOKEN" \
      -o trellis2/ckpts/$f.json \
      https://huggingface.co/microsoft/TRELLIS.2-4B/resolve/main/ckpts/$f.json ; \
    done

# ---- DINOv3 ----
WORKDIR /workspace/ComfyUI/models/facebook/dinov3-vitl16-pretrain-lvd1689m
RUN curl -L -H "Authorization: Bearer $HF_TOKEN" \
    -o model.safetensors \
    https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m/resolve/main/model.safetensors && \
    curl -L -H "Authorization: Bearer $HF_TOKEN" \
    -o config.json \
    https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m/resolve/main/config.json

# ---- UltraShape ----
WORKDIR /workspace/ComfyUI/models/UltraShape
RUN curl -L -o ultrashape_v1.pt \
    https://huggingface.co/Rizzlord/UltraShape/resolve/main/ultrashape_v1.pt

# ---- RMBG ----
WORKDIR /workspace/ComfyUI/models/BiRefNet/RMBG-2.0
RUN curl -L -H "Authorization: Bearer $HF_TOKEN" \
    -o model.safetensors \
    https://huggingface.co/briaai/RMBG-2.0/resolve/main/model.safetensors && \
    curl -L -H "Authorization: Bearer $HF_TOKEN" \
    -o config.json \
    https://huggingface.co/briaai/RMBG-2.0/resolve/main/config.json

# -------------------------
# Serverless handler
# -------------------------
WORKDIR /workspace
COPY handler.py .

CMD ["python3", "handler.py"]
