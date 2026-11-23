"""Generate the synthetic ticket CSVs for the demo and the evaluation.

Usage:  python scripts/make_tickets.py --seed 42

Writes three files with different seeds, so the holdout set is not the set
the rules were written against:
  data/sample_tickets.csv  30 tickets, no labels (the 60-second demo)
  data/dev_labeled.csv     120 labeled tickets (used while writing rules)
  data/test_labeled.csv    150 labeled tickets, half EN half ES (evaluate.py only)

All data is synthetic. Puentara is a fictional company. Card numbers are
made-up 16-digit strings that start with 0000, which no real card does.
"""

import argparse
import csv
import random
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ticket_templates import (GROUPS, MERCHANTS, SCREENS, SECOND_ISSUES,  # noqa: E402
                              SHOWCASE, SUBJECTS)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BASE_COLUMNS = ["ticket_id", "created_at", "channel", "subject", "body"]
LABEL_COLUMNS = ["expected_category", "expected_urgency", "template_language"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
             "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fill_slots(text, lang, rng):
    day = datetime(2026, 9, 1) + timedelta(days=rng.randint(0, 45))
    card = "0000" + "".join(str(rng.randint(0, 9)) for _ in range(12))
    if rng.random() < 0.5:  # people type card numbers with spaces or dashes
        sep = rng.choice([" ", "-"])
        card = sep.join(card[i:i + 4] for i in range(0, 16, 4))
    values = {
        "amount": f"${rng.randint(5, 900)}.{rng.randint(0, 99):02d}",
        "fee": f"${rng.choice(['1.99', '2.50', '4.99', '9.00'])}",
        "date": f"{day.day} de {MONTHS_ES[day.month - 1]}" if lang == "es" else day.strftime("%b %d"),
        "merchant": rng.choice(MERCHANTS),
        "screen": rng.choice(SCREENS[lang]),
        "card": card,
        "cvv": str(rng.randint(100, 999)),
        "otp": str(rng.randint(100000, 999999)),
        "last4": f"{rng.randint(0, 9999):04d}",
    }
    return text.format(**values)


def strip_accents(text):
    # Keep ñ: people who skip accents usually still type ñ.
    out = []
    for ch in text:
        if ch in "ñÑ":
            out.append(ch)
        else:
            out.append("".join(c for c in unicodedata.normalize("NFD", ch)
                               if unicodedata.category(c) != "Mn"))
    return "".join(out)


def add_typo(text, rng):
    words = text.split(" ")
    long_words = [i for i, w in enumerate(words) if len(w) >= 5 and w.isalpha()]
    if not long_words:
        return text
    i = rng.choice(long_words)
    w = words[i]
    j = rng.randint(0, len(w) - 2)
    words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return " ".join(words)


LOW_STAKES = {"fees", "tax_forms", "app_bug", "general_question"}


def add_noise(body, lang, rng, category):
    """Make tickets look like real ones: typos, no accents, caps, two issues."""
    # Second issues are low-stakes topics, so only add them to a more serious
    # main issue; that way the main issue is clearly the label.
    if category not in LOW_STAKES and rng.random() < 0.15:
        end = "" if body[-1] in ".?!" else "."
        body = f"{body}{end} {rng.choice(SECOND_ISSUES[lang])}"
    if lang == "es" and rng.random() < 0.3:
        body = strip_accents(body)
    if rng.random() < 0.15:
        body = add_typo(body, rng)
    if rng.random() < 0.06:
        body = body.upper()
    return body


def make_ticket(group, lang, rng):
    body = add_noise(fill_slots(rng.choice(group[lang]), lang, rng), lang, rng, group["category"])
    return {
        "subject": rng.choice(SUBJECTS[lang]),
        "body": body,
        "expected_category": group["category"],
        "expected_urgency": group["urgency"],
        "template_language": lang,
    }


def finish(tickets, prefix, rng):
    """Add ids, timestamps and channels in order."""
    when = datetime(2026, 10, 12, 8, 0)
    for n, t in enumerate(tickets, start=1):
        when += timedelta(minutes=rng.randint(3, 40))
        t["ticket_id"] = f"{prefix}{n:03d}"
        t["created_at"] = when.strftime("%Y-%m-%d %H:%M")
        t["channel"] = rng.choice(["email", "chat", "web_form"])
    return tickets


def labeled_set(count, prefix, seed):
    rng = random.Random(seed)
    tickets = []
    for i in range(count):
        lang = "en" if i % 2 == 0 else "es"
        tickets.append(make_ticket(rng.choice(GROUPS), lang, rng))
    return finish(tickets, prefix, rng)


def sample_set(seed):
    rng = random.Random(seed)
    tickets = []
    for item in SHOWCASE:
        tickets.append({"subject": item["subject"],
                        "body": fill_slots(item["body"], "en", rng)})
    # One ticket per category, alternating languages, then random ones.
    categories_seen = set()
    for i, group in enumerate(GROUPS):
        if group["category"] in categories_seen:
            continue
        categories_seen.add(group["category"])
        tickets.append(make_ticket(group, "en" if i % 2 == 0 else "es", rng))
    while len(tickets) < 30:
        tickets.append(make_ticket(rng.choice(GROUPS), rng.choice(["en", "es"]), rng))
    rng.shuffle(tickets)
    return finish(tickets, "S", rng)


def write_csv(path, tickets, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel shows accents and ñ correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(tickets)
    print(f"Wrote {len(tickets)} tickets to {path.relative_to(DATA_DIR.parent)}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Generate synthetic Puentara tickets (fictional company).")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    write_csv(DATA_DIR / "sample_tickets.csv", sample_set(args.seed), BASE_COLUMNS)
    write_csv(DATA_DIR / "dev_labeled.csv", labeled_set(120, "D", args.seed + 1),
              BASE_COLUMNS + LABEL_COLUMNS)
    write_csv(DATA_DIR / "test_labeled.csv", labeled_set(150, "T", args.seed + 2),
              BASE_COLUMNS + LABEL_COLUMNS)


if __name__ == "__main__":
    main()
