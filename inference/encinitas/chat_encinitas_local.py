#!/usr/bin/env python3
"""Chat with encinitas using Transformers + PEFT (Gemma 4 MoE LoRA)."""

from __future__ import annotations

import argparse
import os
import re
import sys

ENCINITAS_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ADAPTER_HF = os.environ.get(
    "ENCINITAS_ADAPTER_HF", "coldcurrent/encinitas-gemma4-lora"
)
LOCAL_ADAPTER = os.path.join(ENCINITAS_ROOT, "weights", "encinitas-peft")
LOCAL_OFFLOAD = os.path.join(ENCINITAS_ROOT, "weights", "encinitas-offload")

VENV_CANDIDATES = (
    os.path.join(ENCINITAS_ROOT, "encinitas-venv-gfx1151", "bin", "python"),
    os.path.join(ENCINITAS_ROOT, "encinitas-venv-cuda", "bin", "python"),
    os.path.join(ENCINITAS_ROOT, "encinitas-venv", "bin", "python"),
)
VENV_PYTHON = next(
    (p for p in VENV_CANDIDATES if os.path.isfile(p)),
    VENV_CANDIDATES[-1],
)
ROCM_ENV = {
    "HIP_VISIBLE_DEVICES": "0",
    "HSA_OVERRIDE_GFX_VERSION": "11.5.1",
    "ROCM_PATH": "/usr",
    "AMDGPU_IDS_PATH": "/usr/share/libdrm/amdgpu.ids",
    "PYTHONNOUSERSITE": "1",
    "PYTORCH_ALLOC_CONF": "expandable_segments:True",
    # Avoid parallel CPU->GPU copies that trigger hipErrorInvalidValue on ROCm.
    "HF_DEACTIVATE_ASYNC_LOAD": "1",
}


def ensure_venv() -> None:
    """Re-exec with the project venv if launched via system python3."""
    if not os.path.isfile(VENV_PYTHON):
        return
    venv_root = os.path.dirname(os.path.dirname(os.path.abspath(VENV_PYTHON)))
    if os.path.realpath(sys.prefix) == os.path.realpath(venv_root):
        return
    env = os.environ.copy()
    for key, value in ROCM_ENV.items():
        env.setdefault(key, value)
    if env.get("HF_TOKEN"):
        env.setdefault("HUGGING_FACE_HUB_TOKEN", env["HF_TOKEN"])
    os.execve(VENV_PYTHON, [VENV_PYTHON, os.path.abspath(__file__), *sys.argv[1:]], env)


def patch_safetensors_pread() -> None:
    """Use pread instead of mmap when loading multi-GB safetensors shards.

    Strix Halo reports ~96 GiB VRAM but Linux only shows ~30 GiB system RAM.
    mmap() on 49 GiB shards fails with ENOMEM; disable_mmap=True is worse because
    it reads the entire shard into RAM. pread loads tensor-by-tensor without mmap.
    """
    import safetensors

    if getattr(safetensors, "_encinitas_pread_patch", False):
        return

    original = safetensors.safe_open

    def safe_open_pread(filename, framework, device="cpu", *, backend=None):
        if backend in (None, "mmap"):
            backend = "pread"
        return original(filename, framework, device, backend=backend)

    safetensors.safe_open = safe_open_pread
    safetensors._encinitas_pread_patch = True

    import transformers.modeling_utils as modeling_utils

    modeling_utils.safe_open = safe_open_pread


def is_rocm() -> bool:
    try:
        import torch

        return torch.cuda.is_available() and getattr(torch.version, "hip", None) is not None
    except Exception:
        return False


def configure_rocm_inference() -> None:
    """Use stable attention/math kernels on ROCm.

    gfx1151 nightlies route SDPA through experimental AOTriton flash/mem-efficient
    paths that warn and can hang during Gemma 4 generation. Eager attention plus
    math-only SDPA avoids that backend.
    """
    if not is_rocm():
        return
    import torch

    if getattr(configure_rocm_inference, "_encinitas_rocm_inference_patch", False):
        return
    if hasattr(torch.backends, "cuda"):
        torch.backends.cuda.enable_flash_sdp(False)
        torch.backends.cuda.enable_mem_efficient_sdp(False)
        if hasattr(torch.backends.cuda, "enable_math_sdp"):
            torch.backends.cuda.enable_math_sdp(True)
    configure_rocm_inference._encinitas_rocm_inference_patch = True
    print("ROCm inference: eager attention, math SDPA only")


def resolve_attn_implementation() -> str | None:
    override = os.environ.get("ENCINITAS_ATTN", "").strip().lower()
    if override in {"eager", "sdpa", "flash_attention_2", "flex_attention"}:
        return override
    if is_rocm():
        return "eager"
    return None


def probe_gpu_alloc() -> str | None:
    """Return an error message if ROCm reports a GPU but cannot allocate tensors."""
    if os.environ.get("ENCINITAS_SKIP_GPU_PROBE", "").lower() in {"1", "true", "yes"}:
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        if getattr(torch.version, "hip", None) is None:
            return None
        t = torch.ones(1, device="cuda")
        t += 1
        del t
        torch.cuda.synchronize()
        return None
    except Exception as exc:
        return (
            f"ROCm GPU is visible but tensor allocation failed: {exc}\n"
            "Debian python3-torch-rocm often breaks on gfx1151 (Strix Halo).\n"
            f"Fix: bash {ENCINITAS_ROOT}/fix_encinitas_gfx1151_torch.sh\n"
            f"Then rerun: {ENCINITAS_ROOT}/run_encinitas_local.sh"
        )


def patch_rocm_loading() -> None:
    """Work around ROCm HIP errors during Transformers weight loading on Strix Halo."""
    if not is_rocm():
        return

    import torch
    import transformers.core_model_loading as core_loading
    import transformers.modeling_utils as modeling_utils

    if getattr(core_loading, "_encinitas_rocm_patch", False):
        return

    def as_torch_device(device):
        if device is None:
            return None
        if isinstance(device, torch.device):
            return device
        if isinstance(device, int):
            return torch.device(f"cuda:{device}")
        if isinstance(device, str):
            if device.isdigit():
                return torch.device(f"cuda:{device}")
            if device == "cuda":
                return torch.device("cuda:0")
            return torch.device(device)
        return device

    def materialize_via_cpu(tensor, device=None, dtype=None):
        # Materialize safetensors slice on CPU, cast there, then copy to GPU.
        loaded = tensor[...]
        target = as_torch_device(device)
        if dtype is not None:
            loaded = loaded.to(dtype=dtype)
        if target is not None and target.type == "cuda":
            torch.cuda.synchronize()
            loaded = loaded.to(device=target, non_blocking=False)
            torch.cuda.synchronize()
            return loaded
        if target is not None:
            return loaded.to(device=target)
        return loaded

    core_loading._materialize_copy = materialize_via_cpu
    # Pre-allocating ~25+ GiB in one cudaMalloc often fails on gfx1151 unified memory.
    modeling_utils.caching_allocator_warmup = lambda *args, **kwargs: None
    core_loading._encinitas_rocm_patch = True
    print("ROCm safe loading enabled (no warmup, CPU-staged GPU copies)")


def patch_peft_gemma4() -> None:
    """Skip LoRA injection on Gemma 4 modules PEFT cannot wrap.

    Gemma4ClippableLinear (vision/audio) has no adapter weights.
    Gemma4TextExperts stores MoE weights as 3D Parameters (fused_peft_3d_v1);
    those are merged manually in apply_fused_expert_lora().
    """
    import peft.tuners.lora.model as lora_model
    from transformers.models.gemma4.modeling_gemma4 import (
        Gemma4ClippableLinear,
        Gemma4TextExperts,
    )

    if getattr(lora_model, "_encinitas_gemma4_patch", False):
        return

    original = lora_model.LoraModel._create_and_replace
    skip_types = (Gemma4ClippableLinear, Gemma4TextExperts)

    def create_and_replace_skip_unsupported(
        self,
        lora_config,
        adapter_name,
        target,
        target_name,
        parent,
        current_key,
        *,
        parameter_name=None,
    ):
        if isinstance(target, skip_types):
            return
        return original(
            self,
            lora_config,
            adapter_name,
            target,
            target_name,
            parent,
            current_key,
            parameter_name=parameter_name,
        )

    lora_model.LoraModel._create_and_replace = create_and_replace_skip_unsupported
    lora_model._encinitas_gemma4_patch = True


def language_model_layers(model):
    """Return Gemma 4 text decoder layers from a plain or PEFT-wrapped model."""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    return base.model.language_model.layers


def resolve_adapter_ref() -> str:
    override = os.environ.get("ENCINITAS_ADAPTER_PATH", "").strip()
    if override:
        return override
    if os.path.isfile(os.path.join(LOCAL_ADAPTER, "adapter_model.safetensors")):
        return LOCAL_ADAPTER
    return DEFAULT_ADAPTER_HF


def adapter_files_dir(adapter_ref: str) -> str:
    if os.path.isfile(os.path.join(adapter_ref, "adapter_model.safetensors")):
        return adapter_ref
    from huggingface_hub import snapshot_download

    return snapshot_download(adapter_ref)


def apply_fused_expert_lora(model, adapter_ref: str) -> int:
    """Merge Fireworks fused_peft_3d_v1 expert LoRA into gate_up_proj / down_proj."""
    import json
    import re

    import torch
    from safetensors import safe_open

    adapter_dir = adapter_files_dir(adapter_ref)
    config_path = os.path.join(adapter_dir, "adapter_config.json")
    with open(config_path, encoding="utf-8") as f:
        cfg = json.load(f)
    rank = int(cfg.get("r", 16))
    scale = float(cfg.get("lora_alpha", 32)) / rank

    weights_path = os.path.join(adapter_dir, "adapter_model.safetensors")
    layer_re = re.compile(
        r"base_model\.model\.model\.language_model\.layers\.(\d+)\.experts\."
        r"(?:base_layer\.)?lora_([AB])\.weight"
    )
    by_layer: dict[int, dict[str, dict[str, torch.Tensor]]] = {}

    with safe_open(weights_path, framework="pt", device="cpu") as sf:
        for key in sf.keys():
            match = layer_re.match(key)
            if not match:
                continue
            layer_idx = int(match.group(1))
            ab = match.group(2)
            slot = "gate_up" if ".base_layer." in key else "down"
            by_layer.setdefault(layer_idx, {}).setdefault(slot, {})[f"lora_{ab}"] = (
                sf.get_tensor(key)
            )

    if not by_layer:
        return 0

    layers = language_model_layers(model)
    merged = 0

    def merge_fused(param: torch.nn.Parameter, lora_a: torch.Tensor, lora_b: torch.Tensor):
        num_experts = param.shape[0]
        out_dim, in_dim = param.shape[1], param.shape[2]
        if lora_a.shape[0] != num_experts * rank or lora_b.shape[1] != num_experts * rank:
            raise ValueError(
                f"Fused expert LoRA shape mismatch for {param.shape}: "
                f"A{lora_a.shape} B{lora_b.shape} (rank={rank})"
            )
        a = lora_a.view(num_experts, rank, in_dim)
        b = lora_b.view(out_dim, num_experts, rank).permute(1, 0, 2)
        delta = torch.bmm(b.float(), a.float()) * scale
        param.data.add_(delta.to(device=param.device, dtype=param.dtype))

    for layer_idx in sorted(by_layer):
        if layer_idx >= len(layers):
            continue
        layer = layers[layer_idx]
        if not getattr(layer, "enable_moe_block", False) or not hasattr(layer, "experts"):
            continue
        experts = layer.experts
        tensors = by_layer[layer_idx]
        if "gate_up" in tensors:
            merge_fused(
                experts.gate_up_proj,
                tensors["gate_up"]["lora_A"],
                tensors["gate_up"]["lora_B"],
            )
        if "down" in tensors:
            merge_fused(
                experts.down_proj,
                tensors["down"]["lora_A"],
                tensors["down"]["lora_B"],
            )
        merged += 1

    return merged


ensure_venv()

BASE_MODEL = os.environ.get("ENCINITAS_BASE_MODEL", "google/gemma-4-26B-A4B-it")
ADAPTER_REF = resolve_adapter_ref()
OFFLOAD_DIR = os.environ.get("ENCINITAS_OFFLOAD_DIR", LOCAL_OFFLOAD)


def require_hf_token() -> None:
    if os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        return
    token_file = os.path.expanduser("~/.cache/huggingface/token")
    if os.path.isfile(token_file):
        return
    raise SystemExit(
        "Gemma 4 is gated on Hugging Face.\n"
        "Set HF_TOKEN in encinitas.env (see encinitas.env.example and README.md).\n"
        "Accept the license: https://huggingface.co/google/gemma-4-26B-A4B-it"
    )


def gpu_mem_gib() -> float | None:
    import torch

    override = os.environ.get("ENCINITAS_GPU_MEMORY_GIB", "").strip()
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    if not torch.cuda.is_available():
        return None
    props = torch.cuda.get_device_properties(0)
    reported = props.total_memory / (1024**3)
    # Strix Halo unified memory: some ROCm builds under-report (e.g. 15 GiB vs 90+ GiB).
    if reported < 32 and is_rocm():
        return 96.0
    return reported


def rocm_inference_dtype():
    import torch

    override = os.environ.get("ENCINITAS_DTYPE", "").lower()
    if override in {"bf16", "bfloat16"}:
        return torch.bfloat16
    if override in {"fp16", "float16", "f16"}:
        return torch.float16
    # Debian ROCm builds are much more reliable with fp16 than bf16 on gfx1151.
    return torch.float16 if is_rocm() else torch.bfloat16


def build_load_kwargs():
    import torch

    low_memory = os.environ.get("ENCINITAS_LOW_MEMORY", "").lower() in {
        "1",
        "true",
        "yes",
    }
    vram_gib = gpu_mem_gib()
    dtype = rocm_inference_dtype()
    dtype_name = "fp16" if dtype is torch.float16 else "bf16"

    load_kwargs: dict = {
        "low_cpu_mem_usage": True,
        "trust_remote_code": True,
        "torch_dtype": dtype,
    }
    attn_impl = resolve_attn_implementation()
    if attn_impl:
        load_kwargs["attn_implementation"] = attn_impl
        print(f"Attention implementation: {attn_impl}")

    force_4bit = os.environ.get("ENCINITAS_USE_4BIT", "").lower() in {
        "1",
        "true",
        "yes",
    }

    if low_memory or force_4bit or (vram_gib is not None and vram_gib < 55):
        os.makedirs(OFFLOAD_DIR, exist_ok=True)
        print(f"Low-memory mode (reported VRAM: {vram_gib:.1f} GiB)")
        load_kwargs["device_map"] = "auto"
        load_kwargs["offload_folder"] = OFFLOAD_DIR
        try:
            import bitsandbytes  # noqa: F401
            from transformers import BitsAndBytesConfig

            print("Loading base model in 4-bit")
            load_kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=dtype,
                bnb_4bit_use_double_quant=True,
            )
        except ImportError:
            print(f"Loading {dtype_name} with CPU/GPU/disk offload")
            load_kwargs["max_memory"] = {0: "18GiB", "cpu": "8GiB"}
    else:
        if vram_gib is not None:
            print(
                f"Loading full {dtype_name} model on GPU "
                f"({vram_gib:.1f} GiB VRAM reported)"
            )
        else:
            print(f"Loading full {dtype_name} model on GPU")
        if is_rocm():
            # Sequential layer placement avoids one-shot multi-GB HIP transfers.
            load_kwargs["device_map"] = "auto"
            gpu_budget = max(16, int((vram_gib or 48) * 0.9))
            load_kwargs["max_memory"] = {
                0: f"{gpu_budget}GiB",
                "cpu": "6GiB",
            }
        else:
            load_kwargs["device_map"] = "cuda:0"

    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        hip = getattr(torch.version, "hip", None)
        print(f"GPU: {name}" + (f" (ROCm {hip})" if hip else ""))

    return load_kwargs


def parse_gemma_response(text: str) -> str:
    text = re.sub(
        r"<\|channel>thought\n.*?(?:<\|channel\|>|</channel\|>)",
        "",
        text,
        flags=re.DOTALL,
    )
    text = text.replace("<|channel|>", "").replace("</channel|>", "")
    return text.strip()


def model_device(model):
    import torch

    device = getattr(model, "device", None)
    if device is None and hasattr(model, "hf_device_map"):
        for target in model.hf_device_map.values():
            if isinstance(target, str) and (
                target == "cuda" or target.startswith("cuda:")
            ):
                return torch.device("cuda:0" if target == "cuda" else target)
    if device is None:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    return device


def load_model():
    from peft import PeftModel
    from transformers import AutoTokenizer, Gemma4ForConditionalGeneration

    gpu_err = probe_gpu_alloc()
    if gpu_err:
        raise SystemExit(gpu_err)

    patch_safetensors_pread()
    configure_rocm_inference()
    patch_rocm_loading()
    patch_peft_gemma4()
    print(f"Base model: {BASE_MODEL}")
    print(f"Adapter: {ADAPTER_REF}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    model = Gemma4ForConditionalGeneration.from_pretrained(
        BASE_MODEL, **build_load_kwargs()
    )
    model = PeftModel.from_pretrained(model, ADAPTER_REF, is_trainable=False)
    expert_layers = apply_fused_expert_lora(model, ADAPTER_REF)
    if expert_layers:
        print(f"Merged fused expert LoRA into {expert_layers} MoE layer(s)")
    model.eval()
    return tokenizer, model


def generate(tokenizer, model, messages: list[dict], max_new_tokens: int = 512) -> str:
    import torch

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(text, return_tensors="pt")
    device = model_device(model)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    input_len = inputs["input_ids"].shape[-1]

    print("Generating...", flush=True)
    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=1.0,
            top_p=0.95,
            top_k=64,
        )
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    response = tokenizer.decode(outputs[0][input_len:], skip_special_tokens=False)
    return parse_gemma_response(response)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with encinitas locally")
    parser.add_argument("prompt", nargs="*", help="Single-turn prompt")
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()

    require_hf_token()
    tokenizer, model = load_model()

    if args.prompt:
        reply = generate(
            tokenizer,
            model,
            [{"role": "user", "content": " ".join(args.prompt)}],
            max_new_tokens=args.max_tokens,
        )
        print(reply)
        return

    print("encinitas local (Transformers+PEFT). Ctrl+C to exit.")
    history: list[dict] = []
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user or user in {"/exit", "/quit"}:
            break
        history.append({"role": "user", "content": user})
        reply = generate(tokenizer, model, history, max_new_tokens=args.max_tokens)
        print(f"encinitas> {reply}\n")
        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()