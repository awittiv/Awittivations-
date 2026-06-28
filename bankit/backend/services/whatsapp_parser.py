import re


def parse_loan_request(message_body: str) -> tuple[float | None, str | None]:
    """Extract (amount_inr, purpose) from a WhatsApp message."""
    body = message_body.strip()

    amount_patterns = [
        r"(\d[\d,]*)\s*(?:inr|rupees?|rs\.?)",
        r"(?:inr|rupees?|rs\.?)\s*(\d[\d,]*)",
        r"₹\s*(\d[\d,]*)",
        r"\b(\d{3,6})\b",
    ]

    amount: float | None = None
    for pattern in amount_patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "")
            amount = float(raw)
            break

    purpose_patterns = [
        r"for\s+(.+?)(?:\.|$)",
        r"(?:need|want|require)\s+(?:\w+\s+){0,3}(?:inr|rupees?|rs\.?)\s*[\d,]+\s+(?:for\s+)?(.+?)(?:\.|$)",
        r"(?:purchase|buy|buying|stock|inventory)\s+(.+?)(?:\.|$)",
    ]

    purpose: str | None = None
    for pattern in purpose_patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            purpose = match.group(1).strip()
            break

    if purpose is None and amount is not None:
        purpose = body

    return amount, purpose
