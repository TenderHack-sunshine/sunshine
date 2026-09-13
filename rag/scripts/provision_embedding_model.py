"""One-time external provisioning of local embedding weights.

This script is never invoked by the runtime services.  It exists so a fresh
clone can prepare the same bind-mounted local model directory reproducibly.
"""
from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import snapshot_download


target_root = Path(os.environ.get("MODEL_DIR", "/models"))
target = target_root / "qwen3-embedding-0.6b"
repository = os.environ.get("EMBEDDING_MODEL_REPOSITORY", "Qwen/Qwen3-Embedding-0.6B")

if (target / "config.json").is_file():
    print(f"Embedding model already available at {target}")
else:
    target.mkdir(parents=True, exist_ok=True)
    snapshot_download(repo_id=repository, local_dir=target)
    print(f"Downloaded {repository} to {target}")
