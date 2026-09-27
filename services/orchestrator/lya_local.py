"""Local fine-tuned Lya. Imported only when LYA_MODEL is local."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

BASE_MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
ADAPTER_DIR = Path(__file__).resolve().parent / "lya_adapter"


def adapter_dir(model: str) -> Path | None:
    raw = model.strip()
    if raw == "local":
        path = ADAPTER_DIR
    elif raw.startswith("local:"):
        path = Path(raw.split(":", 1)[1]).expanduser()
    else:
        return None
    if (path / "adapters.safetensors").is_file():
        return path
    return None


@lru_cache(maxsize=1)
def _loaded(path: str):
    from mlx_lm import load

    return load(BASE_MODEL, adapter_path=path)


def generate(path: Path, system: str, user: str) -> str:
    many = generate_many(path, system, [user])
    return many[0] if many else ""


def generate_many(path: Path, system: str, users: list[str]) -> list[str]:
    if not users:
        return []
    from mlx_lm import generate as mlx_generate
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = _loaded(str(path))
    sampler = make_sampler(temp=0)
    outputs: list[str] = []
    for user in users:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        outputs.append(
            mlx_generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=80,
                sampler=sampler,
                verbose=False,
            )
        )
    return outputs
