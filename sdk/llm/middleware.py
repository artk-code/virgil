import logging
from typing import Callable, Awaitable
from sdk.llm.types import LLMResponse, Middleware

logger = logging.getLogger(__name__)

class AuditMiddleware:
    """Log every invoke start/end + redacted input/output to Postgres (or stdout for start)."""
    def __init__(self, db_conn=None):
        self.db_conn = db_conn

    async def __call__(self, call_next, context):
        logger.info(f"[HARNESS] Invoke start provider={context.get('provider')} model={context.get('model')}")
        # TODO: INSERT into advisor_calls (prompt redacted, ts, etc.)
        response = await call_next(context)
        logger.info(f"[HARNESS] Invoke complete. tokens={response.usage}")
        # TODO: UPDATE advisor_calls with response, cost
        return response

class SecurityPIIMiddleware:
    """Redact PII from messages before model call. Critical for security telemetry."""
    async def __call__(self, call_next, context):
        # Simple regex or call to existing VIRGIL PII scrubber
        # For production: integrate with your Meta-scale PII detection if available
        messages = context.get("messages", [])
        for m in messages:
            if isinstance(m.get("content"), str):
                m["content"] = redact_pii(m["content"])  # implement or import
        context["messages"] = messages
        return await call_next(context)

# Example wrapper for LangChain prebuilts (see adapter)
def wrap_langchain_middleware(lc_middleware):
    async def _wrapped(call_next, context):
        # Adapt context <-> LangChain state if needed
        return await lc_middleware(call_next, context)  # or proper integration
    return _wrapped