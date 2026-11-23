"""Sort a CSV of support tickets (English and Spanish) into queues.

Usage:
  python triage.py data/sample_tickets.csv --out output/triaged.csv
  python triage.py data/sample_tickets.csv --summary-lang es
  python triage.py data/sample_tickets.csv --live            (needs ANTHROPIC_API_KEY in .env)
  python triage.py data/sample_tickets.csv --live --record   (also saves answers to fixtures/)

The tool only sorts tickets. It never writes to customers.
Puentara is a fictional company used for the demo.
"""

import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

import config
from ticket_triage.ai import AIError, FixtureClient, LiveClient, RecordingClient
from ticket_triage.route import triage_ticket
from ticket_triage.strings import t


class UserError(Exception):
    """A problem the user can fix; printed as one line, no stack trace."""


def read_tickets(path, lang):
    """Read the CSV and map its headers to the five fields the tool needs."""
    if not path.exists():
        raise UserError(t(lang, "file_missing").format(path=path))
    if not path.is_file():
        raise UserError(t(lang, "not_a_file").format(path=path))
    # utf-8-sig reads UTF-8 files, with or without Excel's BOM. Excel's plain
    # "CSV (Comma delimited)" on Windows saves cp1252 instead, so try that next.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                headers = reader.fieldnames or []
            break
        except UnicodeDecodeError:
            continue
    else:
        raise UserError(t(lang, "bad_encoding").format(path=path))
    # csv.DictReader puts extra values under the key None, usually because a
    # body with commas was not quoted. Stop with the row number instead of guessing.
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        if None in row:
            raise UserError(t(lang, "ragged_row").format(row=number, path=path))
    lookup = {h.strip().lower(): h for h in headers}
    column_for = {}
    for field, aliases in config.COLUMN_ALIASES.items():
        found = next((lookup[a] for a in aliases if a in lookup), None)
        if found is None and field in ("ticket_id", "body"):
            raise UserError(t(lang, "missing_column").format(field=field, names=", ".join(aliases)))
        column_for[field] = found
    tickets = [{field: (row.get(col) or "") if col else "" for field, col in column_for.items()}
               for row in rows]
    return headers, rows, tickets, column_for


def write_output(path, headers, rows, results, column_for):
    """Original columns (subject/body masked) plus the triage columns."""
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = [c for c in config.OUTPUT_COLUMNS if c not in headers]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers + extra)
        writer.writeheader()
        for row, result in zip(rows, results):
            out = dict(row)
            # Never copy card numbers or codes into the output file.
            for field in ("subject", "body"):
                if column_for.get(field):
                    out[column_for[field]] = result[field]
            for col in config.OUTPUT_COLUMNS:
                value = result[col]
                out[col] = str(value).lower() if isinstance(value, bool) else value
            writer.writerow(out)


def print_summary(results, lang, in_path, out_path):
    names = t(lang, "categories")
    print()
    print(t(lang, "title"))
    print(t(lang, "read").format(count=len(results), path=in_path))
    print(t(lang, "wrote").format(path=out_path))

    urgent = [r for r in results if r["urgency"] == "urgent"]
    print()
    print(t(lang, "urgent_header").format(count=len(urgent)))
    for r in urgent:
        print(f'  {r["ticket_id"]:<6} {r["language"]:<7} {names[r["category"]]:<28} {r["reason"]}')
    if not urgent:
        print(t(lang, "none"))

    print()
    print(t(lang, "queue_header"))
    queues = Counter(r["queue"] for r in results)
    for queue in config.QUEUES:
        if queues[queue]:
            print(f'  {t(lang, "queues")[queue]:<30} {queues[queue]:>3}')

    print()
    print(t(lang, "decided_header"))
    decided = Counter(r["decided_by"] for r in results)
    for key in ("rule", "ai", "fallback"):
        print(f'  {t(lang, "decided")[key]:<30} {decided[key]:>3}')

    review = [r for r in results if r["needs_review"]]
    print()
    print(t(lang, "review_header").format(count=len(review)))
    for r in review:
        print(f'  {r["ticket_id"]:<6} {r["language"]:<7} {r["reason"]}')
    if not review:
        print(t(lang, "none"))

    print()
    print(t(lang, "masked").format(count=sum(r["sensitive_data_masked"] for r in results)))
    print(t(lang, "human").format(count=sum(r["needs_human"] for r in results), total=len(results)))


def make_client(args, lang, fixtures_path):
    """Pick live or demo mode and print one line saying which."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if api_key == "your-key-here":  # the placeholder from .env.example
        api_key = ""
    model = os.getenv("ANTHROPIC_MODEL", "").strip() or config.DEFAULT_MODEL
    if args.record and not args.live:
        raise UserError(t(lang, "record_needs_live"))
    if args.live:
        if not api_key:
            raise UserError(t(lang, "need_key"))
        print(t(lang, "live_mode").format(model=model))
        client = LiveClient(api_key, model)
        return (RecordingClient(client) if args.record else client), model
    client = FixtureClient(fixtures_path)
    sources = client.sources()
    if sources == {"recorded"}:
        source = t(lang, "source_recorded")
    elif "recorded" in sources:
        source = t(lang, "source_mixed")
    else:
        source = t(lang, "source_hand")
    key = "demo_with_key" if api_key else "demo_no_key"
    print(t(lang, key).format(source=source))
    return client, model


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Sort EN/ES support tickets into queues (demo company Puentara is fictional).")
    parser.add_argument("input", type=Path, help="CSV file with tickets")
    parser.add_argument("--out", type=Path, default=Path("output/triaged.csv"),
                        help="where to write the result (default: output/triaged.csv)")
    parser.add_argument("--summary-lang", choices=["en", "es"], default="en",
                        help="language for the summary and reasons (default: en)")
    parser.add_argument("--live", action="store_true",
                        help="call Claude for tickets the rules do not decide (needs a key in .env)")
    parser.add_argument("--record", action="store_true",
                        help="with --live: save the real answers to fixtures/ for demo mode")
    parser.add_argument("--fixtures", type=Path, default=config.FIXTURES_FILE, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    # Windows consoles default to an old code page; force UTF-8 so á, ñ and ¿ print.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(config.PROJECT_DIR / ".env")
    args = parse_args(argv)
    lang = args.summary_lang
    try:
        # Check the input first, so a bad path fails before the mode line prints.
        headers, rows, tickets, column_for = read_tickets(args.input, lang)
        client, model = make_client(args, lang, args.fixtures)
        results = [triage_ticket(ticket, client, lang, model) for ticket in tickets]
        write_output(args.out, headers, rows, results, column_for)
    except UserError as error:
        print(error, file=sys.stderr)
        return 2
    except AIError as error:  # only fatal ones reach here (bad key, unknown model)
        detail = t(lang, "ai_problems").get(error.code, error.code)
        print(t(lang, "fatal_ai").format(error=detail), file=sys.stderr)
        return 1
    print_summary(results, lang, args.input, args.out)
    if isinstance(client, RecordingClient):
        count = client.save(args.fixtures)
        print(t(lang, "recorded").format(count=count, path=args.fixtures))
    return 0


if __name__ == "__main__":
    sys.exit(main())
