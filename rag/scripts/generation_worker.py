"""Persistent, local-only Qwen generation worker.

Run this on the demo host (where the local model weights and CPU Torch are
available). Docker reaches it through ``host.docker.internal``; no model is
downloaded and no embedding protocol is modified.
"""
from __future__ import annotations

import argparse
import json
import socketserver
import sys
import threading
import traceback
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class LocalQwen:
    def __init__(self, model_path: Path, model_name: str):
        started = perf_counter()
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as error:  # clear failure rather than a later request crash
            raise RuntimeError("generation worker requires local torch and transformers") from error
        if not model_path.is_dir():
            raise FileNotFoundError(f"local generation model not found: {model_path}")
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        # The verified local Qwen3 weights are bf16. Keeping it on CPU avoids
        # pretending CUDA exists on the Iris Xe demo machine.
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, local_files_only=True, torch_dtype=torch.bfloat16,
        ).to("cpu").eval()
        self.model_name = model_name
        self.load_ms = (perf_counter() - started) * 1000
        self.lock = threading.Lock()

    def generate(self, prompt: str, max_new_tokens: int, max_seconds: float) -> dict:
        started = perf_counter()
        messages = [{"role": "user", "content": prompt}]
        inputs = self.tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                   enable_thinking=False, return_tensors="pt")
        if hasattr(inputs, "input_ids"):
            input_ids = inputs.input_ids
            attention_mask = getattr(inputs, "attention_mask", None)
        else:
            input_ids, attention_mask = inputs, None
        with self.lock, self.torch.inference_mode():
            generated = self.model.generate(input_ids=input_ids, attention_mask=attention_mask,
                                             max_new_tokens=max_new_tokens, do_sample=False,
                                             max_time=max_seconds,
                                             pad_token_id=self.tokenizer.eos_token_id)
        text = self.tokenizer.decode(generated[0][input_ids.shape[-1]:], skip_special_tokens=True).strip()
        # A defensive cleanup for a model/template version that emits thinking.
        if "</think>" in text:
            text = text.split("</think>", 1)[1].strip()
        generated_tokens = int(generated.shape[-1] - input_ids.shape[-1])
        # ``generate`` does not expose a stopping enum here. Reaching the
        # requested cap is unambiguous and must never be treated as complete.
        finish_reason = "length" if generated_tokens >= max_new_tokens else "stop"
        return {"text": text, "model": self.model_name, "device": "cpu", "prompt_tokens": int(input_ids.shape[-1]),
                "generated_tokens": generated_tokens, "truncated": finish_reason == "length",
                "finish_reason": finish_reason, "latency_ms": (perf_counter() - started) * 1000}


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline()
        try:
            request = json.loads(raw.decode("utf-8"))
            if request.get("operation") == "status":
                result = {"ready": True, "model": self.server.model.model_name, "device": "cpu",
                          "model_load_ms": self.server.model.load_ms}
            elif request.get("operation") == "generate":
                prompt = request.get("prompt")
                if not isinstance(prompt, str) or not prompt.strip():
                    raise ValueError("prompt is required")
                max_tokens = int(request.get("max_new_tokens", 160))
                max_seconds = float(request.get("max_seconds", 25))
                if not 1 <= max_tokens <= 512:
                    raise ValueError("max_new_tokens must be between 1 and 512")
                if not 1 <= max_seconds <= 180:
                    raise ValueError("max_seconds must be between 1 and 180")
                result = self.server.model.generate(prompt, max_tokens, max_seconds)
            else:
                raise ValueError("unsupported operation")
        except Exception as error:
            # Keep the client response safe while preserving a useful local
            # failure signal for preflight and operations.
            print(traceback.format_exc(), flush=True)
            result = {"error": f"{type(error).__name__}: {error}"}
        self.wfile.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))


class GenerationServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistent local Qwen generation worker.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "qwen2.5-1.5b-instruct")
    parser.add_argument("--model-name", default="Qwen2.5-1.5B-Instruct")
    args = parser.parse_args()
    server = GenerationServer((args.host, args.port), RequestHandler)
    server.model = LocalQwen(args.model, args.model_name)
    print(json.dumps({"ready": True, "host": args.host, "port": args.port, "model": args.model_name,
                      "device": "cpu", "model_load_ms": round(server.model.load_ms, 1)}, ensure_ascii=False), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
