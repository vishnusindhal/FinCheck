import os

from dotenv import load_dotenv

from backend.app.schemas import MatchResult

load_dotenv()


def _env_amount(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return float(default)
    return float(raw)


AUTO_APPROVE_LIMIT = _env_amount("AUTO_APPROVE_LIMIT", 5000)
DIRECTOR_REVIEW_LIMIT = _env_amount("DIRECTOR_REVIEW_LIMIT", 5000)


def route_approval(invoice: dict, risk: dict, match_result: MatchResult) -> dict:
    total = invoice.get("total_amount") or 0

    if risk["tier"] == "high" or not match_result.matched:
        return {"decision": "needs_review", "approver": "AP Manager"}

    if risk["tier"] == "low" and match_result.matched and total < AUTO_APPROVE_LIMIT:
        return {"decision": "auto_approved", "approver": None}

    if total >= DIRECTOR_REVIEW_LIMIT:
        return {"decision": "needs_review", "approver": "Finance Director"}

    return {"decision": "needs_review", "approver": "AP Team"}
