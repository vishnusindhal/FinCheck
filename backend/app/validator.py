from datetime import datetime

import pycountry

REQUIRED_FIELDS = ["invoice_number", "vendor_name", "invoice_date", "total_amount", "currency"]
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y")
CURRENCY_SYMBOL_MAP = {
    "$": "USD", "₹": "INR", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW", "₽": "RUB",
}


def normalize_currency(currency: str) -> str:
    if not currency:
        return currency
    currency = currency.strip()
    return CURRENCY_SYMBOL_MAP.get(currency, currency.upper())


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_invoice(details: dict | None) -> tuple[bool, list[str]]:
    if not details:
        return False, ["Invoice could not be extracted from the uploaded document."]

    errors = []

    # 1. Required fields aren't null/missing
    for field in REQUIRED_FIELDS:
        value = details.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Missing required field: '{field}'")

    # 2. total_amount > 0 and tax_amount >= 0
    total = details.get("total_amount")
    tax = details.get("tax_amount")
    if total is not None and (not _is_number(total) or total <= 0):
        errors.append(f"'total_amount' must be a positive number, got: {total}")
    if tax is not None and (not _is_number(tax) or tax < 0):
        errors.append(f"'tax_amount' must be >= 0, got: {tax}")

    # 3. invoice_date is a valid date
    date_str = details.get("invoice_date")
    if date_str:
        for fmt in DATE_FORMATS:
            try:
                datetime.strptime(str(date_str), fmt)
                break
            except ValueError:
                continue
        else:
            errors.append(f"'invoice_date' is not a valid date: '{date_str}'")

    # 4. currency is a valid ISO 4217 code (normalize symbols first)
    currency = details.get("currency")
    if currency:
        currency = normalize_currency(str(currency))
        if not pycountry.currencies.get(alpha_3=currency):
            errors.append(f"'currency' is not a valid ISO 4217 code: '{currency}'")

    return len(errors) == 0, errors
