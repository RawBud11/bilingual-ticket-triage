"""Settings in one place: categories, queues, escalation table, model, column names.

Puentara is a fictional company used for this demo.
"""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# --- Claude API -------------------------------------------------------------
# Used when ANTHROPIC_MODEL is not set in .env. A small, fast model is enough
# for sorting tickets into a fixed list of categories.
DEFAULT_MODEL = "claude-haiku-5-5"
AI_TIMEOUT_SECONDS = 30
AI_MAX_TOKENS = 300
# AI answers below this confidence are not trusted: the ticket goes to review.
CONFIDENCE_THRESHOLD = 0.7

PROMPT_FILE = PROJECT_DIR / "prompts" / "triage_system.txt"
FIXTURES_FILE = PROJECT_DIR / "fixtures" / "ai_responses.json"
DEFAULT_TEST_FILE = PROJECT_DIR / "data" / "test_labeled.csv"

# --- Input columns ----------------------------------------------------------
# The tool needs these five fields. Each one accepts several header names, so
# a Zendesk or Freshdesk CSV export works without renaming columns.
# Add your helpdesk's header names here if they differ.
COLUMN_ALIASES = {
    "ticket_id": ["ticket_id", "id", "ticket id", "ticket number"],
    "created_at": ["created_at", "created at", "created time", "requested"],
    "channel": ["channel", "via", "source"],
    "subject": ["subject", "title"],
    "body": ["body", "description", "message", "text"],
}

# --- Categories, urgency and queues ----------------------------------------
CATEGORIES = [
    "account_access",
    "identity_verification",
    "card_lost_stolen",
    "transfer_failed_pending",
    "charge_dispute",
    "fees",
    "tax_forms",
    "app_bug",
    "general_question",
]

URGENCY_LEVELS = ["low", "normal", "high", "urgent"]  # lowest to highest
SENTIMENTS = ["positive", "neutral", "negative"]

# Escalation table. One row per category:
#   default urgency, queue, needs_human
ROUTING = {
    "card_lost_stolen":        ("urgent", "fraud_security", True),
    "charge_dispute":          ("high",   "disputes",       True),
    "account_access":          ("high",   "account_access", True),
    "identity_verification":   ("high",   "account_access", True),
    "transfer_failed_pending": ("high",   "payments",       True),
    "fees":                    ("normal", "billing_tax",    True),
    "tax_forms":               ("normal", "billing_tax",    True),  # no tax advice
    "app_bug":                 ("normal", "tech_support",   False),
    "general_question":        ("low",    "general",        False),
}

# Minimum urgency per category, whoever decides (rule or AI). The AI can
# raise urgency but never below these.
CATEGORY_URGENCY_FLOOR = {
    "card_lost_stolen": "urgent",
    "charge_dispute": "high",
    "account_access": "high",
    "identity_verification": "high",
    "transfer_failed_pending": "high",
}

# Used when the AI answer is missing, invalid or not confident enough.
FALLBACK_URGENCY = "normal"
FALLBACK_QUEUE = "general"
FRAUD_QUEUE = "fraud_security"

QUEUES = ["fraud_security", "disputes", "account_access", "payments",
          "billing_tax", "tech_support", "general"]

# Columns added to the output CSV, after the original columns.
OUTPUT_COLUMNS = [
    "language", "category", "urgency", "sentiment", "queue", "needs_human",
    "needs_review", "decided_by", "confidence", "reason", "sensitive_data_masked",
]
