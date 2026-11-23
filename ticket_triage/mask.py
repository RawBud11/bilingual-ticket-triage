"""Mask card numbers, CVVs and one-time codes before anything else sees them.

Masked text is what the rules read, what the AI receives and what the output
CSV stores. Limit: names, emails and addresses are NOT masked.
"""

import re

CARD_MASK = "[CARD NUMBER MASKED]"
CODE_MASK = "[CODE MASKED]"

# 13 to 19 digits, optionally split by spaces, dashes or dots ("0000 1234 ...").
CARD_RE = re.compile(r"(?<!\d)(?:\d[ .-]?){12,18}\d(?!\d)")

# "CVV 123", "cvc: 1234", "código de seguridad 123".
CVV_RE = re.compile(
    r"\b(cvv2?|cvc|security code|c[oó]digo de seguridad)\b(\D{0,12}?)(\d{3,4})(?!\d)",
    re.IGNORECASE,
)

# "code 482913", "código que me llegó es 482913", "PIN 1234", "OTP: 9921",
# and codes typed in two groups: "código 123 456", "code 123-456".
# Conservative on purpose: it can also hide harmless numbers after these words
# (for example "error code 5003"). Hiding too much is safer than too little.
CODE_RE = re.compile(
    r"\b(one[- ]time code|verification code|otp|code|c[oó]digo|clave|pin|passcode|token)\b"
    r"(\D{0,25}?)(\d{3,4}[ -]\d{3,4}|\d{4,8})(?!\d)",
    re.IGNORECASE,
)


def mask_sensitive(text):
    """Return (masked_text, number_of_items_masked)."""
    count = 0

    def card(_match):
        nonlocal count
        count += 1
        return CARD_MASK

    def keep_label(match):
        nonlocal count
        count += 1
        return f"{match.group(1)}{match.group(2)}{CODE_MASK}"

    text = CARD_RE.sub(card, text or "")
    text = CVV_RE.sub(keep_label, text)
    text = CODE_RE.sub(keep_label, text)
    return text, count
