"""One-time provisioning helper; the demo runtime itself never downloads models."""
from __future__ import annotations

import os
from pathlib import Path

# Conventional streaming is more reliable than Xet's high-memory reconstruction
# on the demo laptop. This affects this one-time provisioning command only.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "models" / "qwen2.5-1.5b-instruct"

if __name__ == "__main__":
    print(snapshot_download("Qwen/Qwen2.5-1.5B-Instruct", local_dir=TARGET))
