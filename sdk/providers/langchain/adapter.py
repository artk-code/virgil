from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
# from langchain.agents.middleware import PIIMiddleware, ToolRetryMiddleware, ... (import actual names from docs)
from sdk.llm.types import LLMResponse, Provider
from sdk.llm.config import LLMConfig
from sdk.providers.langchain.tools import get_virgil_security_tools
from sdk.providers.langchain.prompts import get_advisor_system_prompt
import logging

logger = logging.getLogger(__name__)

class LangChainAdapter(Provider):
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self.model = cfg.model  # e.g. "anthropic:claude-sonnet-4-6" or "fireworks:virgil-advisor"
        # TODO: initialize LangSmith if cfg.langsmith_tracing

    async def invoke(self, messages: list[dict], tools: list = None, **kwargs) -> LLMResponse:
        # Convert our messages to LangChain format if needed
        lc_messages = [SystemMessage(content=get_advisor_system_prompt())] + \
                      [HumanMessage(content=m["content"]) for m in messages if m.get("role") == "user"]

        virgil_tools = get_virgil_security_tools()  # Postgres-backed, safe

        # Build middleware stack (order matters: security first)
        middleware = [
            # SecurityPIIMiddleware(),  # our custom
            # wrap_langchain_middleware(PIIMiddleware()),  # if prebuilt available
            # ToolRetryMiddleware(max_retries=3),
            # SummarizationMiddleware(),  # context compaction
            # HumanInTheLoopMiddleware(approve_tools=["recommend_response_action"]),
            # ModelCallLimitMiddleware(max_calls=50),
            # AuditMiddleware(),  # our custom logging + DB
        ]

        agent = create_agent(
            model=self.model,
            tools=virgil_tools,
            system_prompt=get_advisor_system_prompt(),
            middleware=middleware,  # if supported in your LangChain version; else wrap manually
            # state_schema=...,  # for custom state if needed
        )

        # Run the agent
        result = await agent.ainvoke({"messages": lc_messages})  # or .invoke for sync

        # Parse result into our LLMResponse
        return LLMResponse(
            content=result.get("output", str(result)),
            reasoning=result.get("reasoning"),
            tool_calls=result.get("tool_calls", []),
            usage=result.get("usage", {}),
            provider="langchain",
            model=self.model,
            raw=result
        )