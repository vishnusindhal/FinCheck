"""
Gemini-written one-sentence risk explanation for a report.
(The module name is historical; it explains overall risk signals, not only anomalies.)
"""

import json
import logging

from backend.app.extracter import get_llm

logger = logging.getLogger(__name__)

FALLBACK_TEXT = "Flagged due to multiple risk indicators."

SYSTEM_PROMPT = """
You are an invoice risk explanation engine.

Your task:
- Generate ONE short explanation sentence.
- Use ONLY the provided context.
- Do NOT invent facts.
- Do NOT mention missing fields unless they appear in the signals.
- Keep response under 35 words.
- Sound like an audit assistant, not a chatbot.

Examples:
Input:
{
  "risk_level": "medium",
  "signals": ["Validation error: GST number missing"]
}

Output:
"Flagged because the invoice is missing a GST number."

Input:
{
  "risk_level": "high",
  "signals": ["New/unseen vendor", "Amount 50%+ above vendor average"]
}

Output:
"Flagged because the vendor is new and the invoice amount is significantly higher than similar invoices."
"""


def explanation(context: dict, max_retries: int = 3) -> str:
    """Generate a short plain-English explanation from structured invoice risk signals."""
    payload = json.dumps(context, indent=2, default=str)
    messages = [
        ("system", SYSTEM_PROMPT),
        ("human", f"Generate explanation from this context:\n\n{payload}"),
    ]
    for attempt in range(1, max_retries + 1):
        try:
            response = get_llm().invoke(messages)
            content = response.content
            if isinstance(content, list):  # some models return content blocks
                content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
            text = str(content).strip().replace("\n", " ")
            return text[:250] if text else FALLBACK_TEXT
        except Exception as exc:
            logger.warning("Explanation attempt %d/%d failed: %s", attempt, max_retries, exc)
    return FALLBACK_TEXT


if __name__ == "__main__":
    print(explanation({"risk_level": "high", "risk_score": 55, "signals": ["New/unseen vendor"]}))
