#!/bin/bash
# Nexus Agent OS launch wrapper — sets up CUDA library paths for GPU acceleration
CUDA_LIBS="/home/sinep/ml-env/lib/python3.14/site-packages/nvidia/cu13/lib"
CUDNN_LIBS="/home/sinep/ml-env/lib/python3.14/site-packages/nvidia/cudnn/lib"
export LD_LIBRARY_PATH="$CUDA_LIBS:$CUDNN_LIBS:${LD_LIBRARY_PATH:-}"

cd "$(dirname "$0")"
exec .venv/bin/python main.py
