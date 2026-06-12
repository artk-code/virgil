import os
from typing import Any
from sdk.llm.config import load_config, LLMConfig
from sdk.llm.types import LLMResponse, Provider, Middleware
from sdk.llm.middleware import AuditMiddleware, SecurityPIIMiddleware

# Registry of providers
PROVIDERS: dict[str, type[Provider]] = {}

def register_provider(name: str, cls: type[Provider]):
    PROVIDERS[name] = cls

async def get_harness(provider: str | None = None) -> Provider:
    cfg = load_config()
    provider = provider or cfg.provider
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}. Registered: {list(PROVIDERS)}")
    return PROVIDERS[provider](cfg)

# Convenience high-level API used by python-worker / go-api
async def advise_on_event(event: dict, provider: str | None = None, **kwargs) -> LLMResponse:
    harness = await get_harness(provider)
    # Build messages + tools from event using utils
    messages = build_advisor_messages(event)  # in utils.py
    tools = get_virgil_tools()                # from providers or shared
    return await harness.invoke(messages=messages, tools=tools, **kwargs)