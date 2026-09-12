from __future__ import annotations

from typing import Iterable

import numpy as np
import torch
from tqdm.auto import tqdm
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_sequence_classifier(model_name_or_path: str, device: torch.device | None = None):
    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
    model = AutoModelForSequenceClassification.from_pretrained(model_name_or_path)
    device = device or get_device()
    model.to(device)
    model.eval()
    return tokenizer, model


def positive_probabilities(logits: torch.Tensor) -> torch.Tensor:
    if logits.shape[-1] == 1:
        return torch.sigmoid(logits[:, 0])
    return torch.softmax(logits, dim=-1)[:, 1]


def toxicity_obscenity_probabilities(
    model: AutoModelForSequenceClassification,
    logits: torch.Tensor,
) -> torch.Tensor:
    config = model.config
    id2label = {int(k): str(v).lower() for k, v in config.id2label.items()}
    obscenity_ids = [
        idx
        for idx, label in id2label.items()
        if any(key in label for key in ("obscen", "profan", "мат", "obscene"))
    ]
    if logits.shape[-1] == 1:
        return torch.sigmoid(logits[:, 0])
    if obscenity_ids:
        probs = torch.sigmoid(logits) if getattr(config, "problem_type", None) == "multi_label_classification" else torch.softmax(logits, dim=-1)
        return probs[:, obscenity_ids].max(dim=1).values
    probs = torch.sigmoid(logits) if logits.shape[-1] > 2 else torch.softmax(logits, dim=-1)
    if probs.shape[-1] == 2:
        return probs[:, 1]
    return probs.max(dim=1).values


def _window_token_ids(input_ids: list[int], max_content_len: int, stride: int) -> Iterable[list[int]]:
    if len(input_ids) <= max_content_len:
        yield input_ids
        return
    step = max(max_content_len - stride, 1)
    start = 0
    while start < len(input_ids):
        yield input_ids[start : start + max_content_len]
        if start + max_content_len >= len(input_ids):
            break
        start += step


def _encode_token_id_window(tokenizer, chunk_ids: list[int], max_length: int) -> dict[str, torch.Tensor]:
    if tokenizer.cls_token_id is not None and tokenizer.sep_token_id is not None:
        ids = [tokenizer.cls_token_id] + chunk_ids + [tokenizer.sep_token_id]
    elif tokenizer.bos_token_id is not None and tokenizer.eos_token_id is not None:
        ids = [tokenizer.bos_token_id] + chunk_ids + [tokenizer.eos_token_id]
    else:
        ids = chunk_ids
    ids = ids[:max_length]
    attention_mask = [1] * len(ids)
    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        pad_token_id = 0
    pad_len = max_length - len(ids)
    if pad_len > 0:
        ids = ids + [pad_token_id] * pad_len
        attention_mask = attention_mask + [0] * pad_len
    return {
        "input_ids": torch.tensor([ids], dtype=torch.long),
        "attention_mask": torch.tensor([attention_mask], dtype=torch.long),
    }


@torch.inference_mode()
def predict_transformer_sliding(
    texts: list[str],
    tokenizer,
    model: AutoModelForSequenceClassification,
    max_length: int = 256,
    stride: int = 64,
    batch_size: int = 32,
    probability_mode: str = "binary",
    show_progress: bool = False,
) -> np.ndarray:
    device = next(model.parameters()).device
    special_tokens = tokenizer.num_special_tokens_to_add(pair=False)
    max_content_len = max(max_length - special_tokens, 1)
    text_window_map: list[int] = []
    encodings: list[dict[str, torch.Tensor]] = []

    for text_idx, text in enumerate(texts):
        ids = tokenizer(str(text), add_special_tokens=False)["input_ids"]
        for chunk_ids in _window_token_ids(ids, max_content_len=max_content_len, stride=stride):
            encoded = _encode_token_id_window(tokenizer, chunk_ids, max_length)
            encodings.append(encoded)
            text_window_map.append(text_idx)

    max_probs = np.zeros(len(texts), dtype=np.float32)
    iterator = range(0, len(encodings), batch_size)
    if show_progress:
        iterator = tqdm(iterator, desc="transformer inference")

    for start in iterator:
        batch = encodings[start : start + batch_size]
        input_ids = torch.cat([item["input_ids"] for item in batch]).to(device)
        attention_mask = torch.cat([item["attention_mask"] for item in batch]).to(device)
        logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
        if probability_mode == "toxicity_obscenity":
            probs = toxicity_obscenity_probabilities(model, logits)
        else:
            probs = positive_probabilities(logits)
        for offset, prob in enumerate(probs.detach().cpu().numpy()):
            text_idx = text_window_map[start + offset]
            max_probs[text_idx] = max(max_probs[text_idx], float(prob))
    return max_probs
