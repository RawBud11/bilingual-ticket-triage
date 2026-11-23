"""The AI step: build the request, call Claude (or read a fixture), check the answer.

Three clients share one method, complete(request) -> raw text:
  LiveClient       real call through the official anthropic SDK (--live)
  FixtureClient    demo mode: saved answers from fixtures/ai_responses.json
  RecordingClient  wraps LiveClient and saves its answers (--live --record)
Any problem raises AIError. The caller turns it into "needs review".
"""

import json
import re
from datetime import date

import config

LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}


class AIError(Exception):
    """An AI problem. `code` is a key in strings.py "ai_problems".

    fatal=True means every ticket would fail the same way (bad key, unknown
    model), so the run stops with a clear message instead of 30 fallbacks.
    """

    def __init__(self, code, fatal=False):
        super().__init__(code)
        self.code = code
        self.fatal = fatal


TICKET_TAG_RE = re.compile(r"<\s*/?\s*ticket\s*>", re.IGNORECASE)


def strip_tags(text):
    """Remove <ticket> / </ticket> typed by a customer, so ticket text cannot
    "close" the ticket block and pretend to be instructions."""
    return TICKET_TAG_RE.sub("[tag removed]", text)


def build_request(ticket_id, subject, body, reason_lang, model):
    """Build the API request. Subject and body must already be masked."""
    system = config.PROMPT_FILE.read_text(encoding="utf-8")
    system = (system.replace("{categories}", ", ".join(config.CATEGORIES))
                    .replace("{reason_language}", LANGUAGE_NAMES[reason_lang]))
    user = f"<ticket>\nSubject: {strip_tags(subject)}\nBody: {strip_tags(body)}\n</ticket>"
    return {
        "ticket_id": ticket_id,      # used by fixtures, not sent to the API
        "reason_lang": reason_lang,  # same
        "model": model,
        "max_tokens": config.AI_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }


def parse_ai_response(text):
    """Turn the model's text into a checked dict, or raise AIError."""
    # Models sometimes wrap JSON in ```json fences or add a sentence; take the
    # first {...} block and ignore the rest.
    found = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not found:
        raise AIError("bad_json")
    try:
        data = json.loads(found.group(0))
    except json.JSONDecodeError:
        raise AIError("bad_json") from None
    if not isinstance(data, dict):
        raise AIError("bad_json")
    if data.get("category") not in config.CATEGORIES:
        raise AIError("bad_category")
    if data.get("urgency") not in config.URGENCY_LEVELS:
        raise AIError("bad_urgency")
    if data.get("sentiment") not in config.SENTIMENTS:
        raise AIError("bad_sentiment")
    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) \
            or not 0 <= confidence <= 1:
        raise AIError("bad_confidence")
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise AIError("bad_reason")
    return {
        "category": data["category"],
        "urgency": data["urgency"],
        "sentiment": data["sentiment"],
        "confidence": float(confidence),
        "reason": " ".join(reason.split())[:200],  # one line, not too long
    }


class LiveClient:
    def __init__(self, api_key, model, sdk_client=None):
        # Imported here, not at the top: the SDK takes seconds to load and
        # demo mode does not need it.
        import anthropic
        self.model = model
        # sdk_client lets tests pass a fake, so tests never touch the network.
        self.sdk = sdk_client or anthropic.Anthropic(
            api_key=api_key, timeout=config.AI_TIMEOUT_SECONDS, max_retries=2)

    def complete(self, request):
        import anthropic  # already loaded by __init__, so this is instant
        try:
            response = self.sdk.messages.create(
                model=request["model"], max_tokens=request["max_tokens"],
                system=request["system"], messages=request["messages"])
        except anthropic.AuthenticationError:
            raise AIError("auth", fatal=True) from None
        except anthropic.PermissionDeniedError:
            raise AIError("permission", fatal=True) from None
        except anthropic.NotFoundError:
            raise AIError("model", fatal=True) from None
        except anthropic.APITimeoutError:
            raise AIError("timeout") from None
        except anthropic.APIConnectionError:
            raise AIError("connection") from None
        except anthropic.RateLimitError:
            raise AIError("rate_limit") from None
        except anthropic.BadRequestError:
            raise AIError("bad_request") from None
        except anthropic.APIError:
            raise AIError("server") from None
        return "".join(block.text for block in response.content
                       if getattr(block, "type", "") == "text")


class FixtureClient:
    """Demo mode. Fixture file layout:
    {"responses": {"S004": {"en": {"source": "hand-written", "response": {...}}}}}
    "response" is a JSON object, or a string for raw (possibly broken) text.
    """

    def __init__(self, path=config.FIXTURES_FILE):
        with open(path, encoding="utf-8") as f:
            self.responses = json.load(f).get("responses", {})

    def sources(self):
        """Set of labels in the file: {"hand-written"}, {"recorded"} or both."""
        return {entry["source"] for by_lang in self.responses.values()
                for entry in by_lang.values()}

    def complete(self, request):
        entry = self.responses.get(request["ticket_id"], {}).get(request["reason_lang"])
        if entry is None:
            raise AIError("no_fixture")
        response = entry["response"]
        return response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)


class RecordingClient:
    """Calls the live client and keeps every raw answer, to save as fixtures."""

    def __init__(self, live_client):
        self.live = live_client
        self.recorded = []  # (ticket_id, lang, raw_text)

    def complete(self, request):
        text = self.live.complete(request)
        self.recorded.append((request["ticket_id"], request["reason_lang"], text))
        return text

    def save(self, path=config.FIXTURES_FILE):
        """Merge recorded answers into the fixture file, labeled "recorded"."""
        data = {"responses": {}}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        today = date.today().isoformat()
        for ticket_id, lang, text in self.recorded:
            try:
                response = json.loads(text)  # store readable JSON when possible
            except json.JSONDecodeError:
                response = text
            data.setdefault("responses", {}).setdefault(ticket_id, {})[lang] = {
                "source": "recorded", "model": self.live.model,
                "recorded_at": today, "response": response}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return len(self.recorded)
