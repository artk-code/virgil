# Utility functions for VIRGIL LLM Harness

def build_advisor_messages(event: dict) -> list[dict]:
    """Build prompt messages from a VIRGIL security event. Stub for now - expand with context engineering."""
    return [
        {"role": "user", "content": f"Analyze this security event and provide reasoning + recommended action: {event}"}
    ]

def get_virgil_tools():
    """Return list of VIRGIL security tools. For LangChain path, import from providers.langchain.tools."""
    from sdk.providers.langchain.tools import query_recent_events, get_finding_details, recommend_response_action
    return [query_recent_events, get_finding_details, recommend_response_action]

def redact_pii(text: str) -> str:
    """Basic PII redaction stub. Replace with production scrubber."""
    # TODO: Integrate real PII detection (regex + ML if available in VIRGIL)
    import re
    # Simple example patterns
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED-SSN]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[REDACTED-EMAIL]', text)
    return text