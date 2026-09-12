"""Download the official CPU-friendly Qwen3-8B GGUF model once."""
from __future__ import annotations

import os
from pathlib import Path

# Conventional streaming is more reliable than Xet's high-memory reconstruction
# on the demo laptop. This affects this one-time provisioning command only.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
from huggingface_hub import hf_hub_download


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "qwen3-8b"
REPOSITORY = "Qwen/Qwen3-8B-GGUF"
FILENAME = "Qwen3-8B-Q4_K_M.gguf"

if __name__ == "__main__":
    TARGET.mkdir(parents=True, exist_ok=True)
    print(hf_hub_download(repo_id=REPOSITORY, filename=FILENAME, local_dir=TARGET))
