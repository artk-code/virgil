#!/usr/bin/env python3
"""Upload encinitas LoRA adapter to a public Hugging Face repo.

Reads HF_TOKEN from the environment or ~/.cache/huggingface/token only.
Never hardcode tokens in this script or commit them to git.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_REPO = "coldcurrent/encinitas-gemma4-lora"
DEFAULT_SOURCE = Path(__file__).resolve().parent / "weights" / "encinitas-peft"

MODEL_CARD = """---
license: mit
base_model: google/gemma-4-26B-A4B-it
tags:
  - lora
  - gemma4
  - moe
  - peft
  - encinitas
library_name: peft
pipeline_tag: text-generation
---

# encinitas-gemma4-lora

LoRA adapter for **encinitas** on [Gemma 4 26B A4B](https://huggingface.co/google/gemma-4-26B-A4B-it).

Uses Fireworks `fused_peft_3d_v1` MoE expert layout. Load with VIRGIL inference scripts:

https://github.com/artk-code/virgil/tree/main/inference/encinitas

```bash
git clone https://github.com/artk-code/virgil.git
cd virgil/inference/encinitas
cp encinitas.env.example encinitas.env   # add HF_TOKEN locally
bash fix_encinitas_gfx1151_torch.sh      # AMD Strix Halo
./run_encinitas_local.sh "Your prompt"
```

## Requirements

- 48 GiB+ VRAM (fp16) or low-memory mode
- Accept [Gemma 4 license](https://huggingface.co/google/gemma-4-26B-A4B-it)

## License

- Scripts in [artk-code/virgil](https://github.com/artk-code/virgil): MIT
- Adapter weights: MIT
- Base Gemma 4: Google Gemma license (accept on Hugging Face)
"""


def require_token() -> str:
    token = (
        os.environ.get("HF_TOKEN", "").strip()
        or os.environ.get("HUGGING_FACE_HUB_TOKEN", "").strip()
    )
    if token:
        return token
    token_file = Path.home() / ".cache" / "huggingface" / "token"
    if token_file.is_file():
        return token_file.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "Set HF_TOKEN in your environment (do not commit it).\n"
        "Create a token at https://huggingface.co/settings/tokens"
    )


def validate_source(source: Path) -> None:
    for name in ("adapter_model.safetensors", "adapter_config.json"):
        if not (source / name).is_file():
            raise SystemExit(f"Missing {name} in {source}")


def enrich_adapter_config(source: Path) -> dict:
    cfg = json.loads((source / "adapter_config.json").read_text(encoding="utf-8"))
    cfg.setdefault("base_model_name_or_path", "google/gemma-4-26B-A4B-it")
    cfg.setdefault("fw_lora_layout", "fused_peft_3d_v1")
    cfg["inference_mode"] = True
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"Not found: {source}")

    validate_source(source)
    token = require_token()

    from huggingface_hub import HfApi, create_repo

    api = HfApi(token=token)
    who = api.whoami()
    print(f"Logged in as: {who.get('name', who.get('fullname', 'unknown'))}")

    create_repo(args.repo, repo_type="model", private=args.private, exist_ok=True, token=token)
    print(f"Repository: https://huggingface.co/{args.repo}")

    uploads: list[tuple[Path, str]] = []
    for name in ("adapter_model.safetensors", "tokenizer.json", "tokenizer_config.json"):
        path = source / name
        if path.is_file():
            uploads.append((path, name))

    cfg_path = source / ".upload_adapter_config.json"
    cfg_path.write_text(json.dumps(enrich_adapter_config(source), indent=2) + "\n", encoding="utf-8")
    uploads.append((cfg_path, "adapter_config.json"))

    readme_path = source / ".upload_README.md"
    readme_path.write_text(MODEL_CARD, encoding="utf-8")
    uploads.append((readme_path, "README.md"))

    for local_path, remote_name in uploads:
        mib = local_path.stat().st_size / (1024 * 1024)
        print(f"Uploading {remote_name} ({mib:.1f} MiB)...")
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=remote_name,
            repo_id=args.repo,
            repo_type="model",
            token=token,
        )

    cfg_path.unlink(missing_ok=True)
    readme_path.unlink(missing_ok=True)
    print(f"Done: https://huggingface.co/{args.repo}")


if __name__ == "__main__":
    main()