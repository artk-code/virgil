from dataclasses import dataclass, field
from typing import Protocol, Any, Callable, Awaitable
from pydantic import BaseModel

@dataclass
class LLMResponse:
    content: str
    reasoning: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    provider: str = "unknown"
    model: str = "unknown"
    raw: Any = None  # original response for debugging

class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict  # JSON schema

class Provider(Protocol):
    async def invoke(
        self,
        messages: list[dict],
        tools: list[ToolSpec] | None = None,
        **kwargs
    ) -> LLMResponse: ...

class Middleware(Protocol):
    async def __call__(
        self,
        call_next: Callable[..., Awaitable[LLMResponse]],
        context: dict,  # contains messages, tools, config, etc.
    ) -> LLMResponse: ...