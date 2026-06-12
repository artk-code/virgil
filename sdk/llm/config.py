import os
from pydantic import BaseModel, Field

class LLMConfig(BaseModel):
    provider: str = Field(default="langchain", env="VIRGIL_LLM_PROVIDER")
    model: str = Field(default="anthropic:claude-sonnet-4-6", env="VIRGIL_LLM_MODEL")
    temperature: float = Field(default=0.1, env="VIRGIL_LLM_TEMPERATURE")
    max_tokens: int = Field(default=4096, env="VIRGIL_LLM_MAX_TOKENS")
    langsmith_tracing: bool = Field(default=False, env="VIRGIL_LANGSMITH_TRACING")
    api_key: str | None = Field(default=None, env="VIRGIL_LLM_API_KEY")  # or per-provider

    class Config:
        env_file = ".env"
        extra = "ignore"

def load_config() -> LLMConfig:
    return LLMConfig()