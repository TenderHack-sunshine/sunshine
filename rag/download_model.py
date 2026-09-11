from huggingface_hub import snapshot_download

MODEL_NAME = "Qwen/Qwen3-4B"
LOCAL_DIR = "models/qwen3-4b"

snapshot_download(
    repo_id=MODEL_NAME,
    local_dir=LOCAL_DIR,
    local_dir_use_symlinks=False,
)

print(f"Model downloaded to: {LOCAL_DIR}")

