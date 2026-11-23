"""Triage one ticket: mask -> detect language -> rules -> AI -> route.

Safety rules applied here, whoever decided the category:
- urgency never goes below the rule floor or the category floor
- fraud wording and lost/stolen cards go to the fraud_security queue
- money, dispute and access categories always need a human
- anything the AI could not answer well goes to review, never guessed
"""

import config

from .ai import AIError, build_request, parse_ai_response
from .language import detect_language
from .mask import mask_sensitive
from .rules import apply_rules, higher_urgency
from .strings import t


def triage_ticket(ticket, client, lang, model=config.DEFAULT_MODEL,
                  threshold=config.CONFIDENCE_THRESHOLD):
    """Return a dict with the masked text and every output column.

    ticket: dict with ticket_id, subject, body.
    client: anything with complete(request) -> text (see ai.py).
    lang:   "en" or "es", the language for reasons shown to the team.
    """
    subject, masked_a = mask_sensitive(ticket.get("subject", ""))
    body, masked_b = mask_sensitive(ticket.get("body", ""))
    text = f"{subject}\n{body}"
    language = detect_language(text)
    rule = apply_rules(text)

    sentiment, confidence, fallback = "", "", False
    if rule.category:
        decided_by = "rule"
        category = rule.category
        urgency = config.ROUTING[category][0]
        reason = f'{t(lang, "rule_reasons")[rule.rule_id]} ("{rule.matched}")'
    else:
        request = build_request(ticket["ticket_id"], subject, body, lang, model)
        try:
            answer = parse_ai_response(client.complete(request))
        except AIError as error:
            if error.fatal:
                raise
            fallback = True
            confidence = ""
            detail = t(lang, "ai_problems").get(error.code, error.code)
            reason = t(lang, "fallback_reasons")["invalid"].format(detail=detail)
        else:
            confidence = f'{answer["confidence"]:.2f}'
            sentiment = answer["sentiment"]
            if answer["confidence"] < threshold:
                fallback = True
                reason = t(lang, "fallback_reasons")["low_confidence"].format(
                    confidence=answer["confidence"], threshold=threshold)
            else:
                decided_by = "ai"
                category = answer["category"]
                urgency = answer["urgency"]
                reason = answer["reason"]

    if fallback:
        decided_by = "fallback"
        category = ""  # unknown: a person decides
        urgency = config.FALLBACK_URGENCY
        queue = config.FALLBACK_QUEUE
        needs_human = True
    else:
        _, queue, needs_human = config.ROUTING[category]
        if rule.fraud:
            queue = config.FRAUD_QUEUE
            needs_human = True

    # The floors: nothing after the rules can make a ticket less urgent.
    urgency = higher_urgency(urgency, rule.floor)
    urgency = higher_urgency(urgency, config.CATEGORY_URGENCY_FLOOR.get(category))

    # "Urgent" means fraud, a lost card or someone else in the account (see the
    # prompt), so every urgent ticket goes to fraud and security, even when the
    # AI picked a category like charge_dispute.
    if urgency == "urgent":
        queue = config.FRAUD_QUEUE
        needs_human = True

    needs_review = fallback
    if language == "other":
        needs_review = True
        needs_human = True
        if not fallback:
            reason = f'{reason}. {t(lang, "fallback_reasons")["other_language"]}'

    return {
        "ticket_id": ticket["ticket_id"],
        "subject": subject,
        "body": body,
        "language": language,
        "category": category,
        "urgency": urgency,
        "sentiment": sentiment,
        "queue": queue,
        "needs_human": needs_human,
        "needs_review": needs_review,
        "decided_by": decided_by,
        "confidence": confidence,
        "reason": reason,
        "sensitive_data_masked": (masked_a + masked_b) > 0,
    }
