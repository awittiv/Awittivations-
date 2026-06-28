import anthropic
from backend.config import settings
from backend.prompts.aave_schema import AAVE_V3_SCHEMA_PROMPT

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


async def nl_to_sql(question: str) -> str:
    """Translate a natural language DeFi question into a SQL query via Claude."""
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=AAVE_V3_SCHEMA_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    return message.content[0].text.strip()


async def repair_sql(question: str, bad_sql: str, error: str) -> str:
    """Given SQL that failed to execute, ask Claude to fix it using the DB error."""
    repair_prompt = f"""The SQL below was generated for a user's question but failed to execute against the database.

User question: "{question}"

SQL that failed:
{bad_sql}

Database error:
{error}

Return a corrected SQL query that resolves this error and answers the question.
Output ONLY the raw SQL — no explanation, no markdown code fences.""".strip()

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=AAVE_V3_SCHEMA_PROMPT,
        messages=[{"role": "user", "content": repair_prompt}],
    )
    return message.content[0].text.strip()


async def explain_results(question: str, sql: str, rows: list[dict]) -> str:
    """Have Claude summarize query results in plain English for the user."""
    summary_prompt = f"""
The user asked: "{question}"

SQL executed:
{sql}

Results (up to 20 rows):
{rows}

Write a 2-3 sentence plain-English summary of what these results mean for a DeFi investor.
Focus on actionable insights. Be concise.
""".strip()

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": summary_prompt}],
    )
    return message.content[0].text.strip()
