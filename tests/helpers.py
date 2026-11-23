"""Small fakes shared by the tests. No network, no API key."""

import json


class FakeAI:
    """Returns a fixed answer and remembers every request it got."""

    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer)


def ai_answer(category="general_question", urgency="low", sentiment="neutral",
              confidence=0.9, reason="test reason"):
    return {"category": category, "urgency": urgency, "sentiment": sentiment,
            "confidence": confidence, "reason": reason}


def ticket(body, subject="", ticket_id="X001"):
    return {"ticket_id": ticket_id, "subject": subject, "body": body}
