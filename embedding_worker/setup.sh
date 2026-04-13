#!/bin/bash
# Embedding Worker Setup - Separate venv, no PyTorch
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
MODEL_DIR="$SCRIPT_DIR/model"
MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"

echo "=== Embedding Worker Setup ==="

# Step 1: Create venv
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV_DIR"
else
    echo "Venv exists."
fi

# Step 2: Install dependencies
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q

# Step 3: Download ONNX model
if [ ! -f "$MODEL_DIR/model.onnx" ]; then
    echo "Downloading ONNX model..."
    mkdir -p "$MODEL_DIR"
    "$VENV_DIR/bin/python" -c "
from huggingface_hub import hf_hub_download
import shutil, os

model_dir = '$MODEL_DIR'
repo = '$MODEL_NAME'

# Download ONNX model file
for filename in ['onnx/model.onnx', 'tokenizer.json', 'config.json']:
    path = hf_hub_download(repo_id=repo, filename=filename)
    basename = os.path.basename(filename)
    shutil.copy2(path, os.path.join(model_dir, basename))
    print(f'  Downloaded: {basename}')

print('Model download complete.')
"
else
    echo "Model already downloaded."
fi

# Step 4: Verify
echo ""
echo "=== Verification ==="
"$VENV_DIR/bin/python" -c "
import onnxruntime, tokenizers, numpy
print(f'onnxruntime: {onnxruntime.__version__}')
print(f'tokenizers:  {tokenizers.__version__}')
print(f'numpy:       {numpy.__version__}')
"

echo ""
"$VENV_DIR/bin/python" "$SCRIPT_DIR/worker.py" embed "test" > /dev/null && echo "Worker: OK" || echo "Worker: FAILED"

echo ""
echo "=== Setup Complete ==="
echo "Worker:  $SCRIPT_DIR/worker.py"
echo "Venv:    $VENV_DIR"
echo "Model:   $MODEL_DIR"
