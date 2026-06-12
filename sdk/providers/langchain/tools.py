from langchain_core.tools import tool
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_URL = os.getenv("DATABASE_URL", "postgresql://...")

def get_db_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

@tool
def query_recent_events(host_id: str | None = None, limit: int = 20) -> list[dict]:
    """Query recent security events from VIRGIL Postgres. Use for context on investigations."""
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            if host_id:
                cur.execute("SELECT * FROM events WHERE host_id = %s ORDER BY ts DESC LIMIT %s", (host_id, limit))
            else:
                cur.execute("SELECT * FROM events ORDER BY ts DESC LIMIT %s", (limit,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

@tool
def get_finding_details(finding_id: str) -> dict:
    """Retrieve full details + history for a specific finding."""
    # Similar Postgres query on findings table
    ...

@tool
def recommend_response_action(event_json: str) -> str:
    """Given an event or finding, recommend concrete response (isolate host, block IP, etc.). Returns structured JSON string."""
    # The model will call this; we can also make it deterministic in middleware if needed
    ...