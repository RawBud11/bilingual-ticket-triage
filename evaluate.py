"""Measure the triage on the labeled synthetic holdout set (data/test_labeled.csv).

Usage:
  python evaluate.py                     rules layer only (demo mode, no API calls)
  python evaluate.py --live              full pipeline with Claude (needs a key in .env)
  python evaluate.py --summary-lang es   output in Spanish

In demo mode the AI answers come from hand-written fixtures, so scoring them
would measure nothing. Demo mode reports the RULES LAYER only: how many
tickets the rules decide, how often they are right, and how many urgent
tickets they catch. Full-pipeline numbers only come from --live.
"""

import argparse
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

import config
from ticket_triage.ai import AIError, LiveClient
from ticket_triage.route import triage_ticket
from ticket_triage.strings import t

TEXT = {
    "en": {
        "label": "Synthetic sample data (template-generated). These numbers show the tool works on this "
                 "test set, not how accurate it would be on real tickets.",
        "rules_mode": "Mode: rules layer only (demo, no API calls). Run with --live for full-pipeline numbers.",
        "live_mode": "Mode: full pipeline with Claude ({model}).",
        "tickets": "Tickets in test set",
        "coverage": "Rules coverage (decided by rules)",
        "rule_cat": "Category accuracy, rule-decided tickets",
        "rule_urg": "Urgency accuracy, rule-decided tickets",
        "urgent_rules": "Urgent-ticket recall (rules alone)",
        "cat": "Category accuracy, all tickets",
        "urg": "Urgency accuracy, all tickets",
        "urgent_all": "Urgent-ticket recall (full pipeline)",
        "review": "Sent to review (fallback)",
        "misses": "Misses",
        "expected": "expected",
        "got": "got",
        "by": {"rule": "rule", "ai": "AI", "fallback": "not decided"},
        "no_misses": "  none",
        "need_key": "--live needs an API key. Add ANTHROPIC_API_KEY to .env, or run without --live.",
        "missing": "Test file not found: {path}. Create it with: python scripts/make_tickets.py --seed 42",
        "not_labeled": "{path} has no expected_category / expected_urgency columns, so there is nothing to compare. "
                       "Use a labeled file such as data/test_labeled.csv.",
    },
    "es": {
        "label": "Datos sintéticos de ejemplo (generados con plantillas). Estos números muestran que la "
                 "herramienta funciona con este conjunto de prueba, no su precisión con tickets reales.",
        "rules_mode": "Modo: solo la capa de reglas (demo, sin llamadas a la API). Usa --live para medir todo el proceso.",
        "live_mode": "Modo: proceso completo con Claude ({model}).",
        "tickets": "Tickets en el conjunto de prueba",
        "coverage": "Cobertura de reglas (decididos por reglas)",
        "rule_cat": "Precisión de categoría, decididos por reglas",
        "rule_urg": "Precisión de urgencia, decididos por reglas",
        "urgent_rules": "Urgentes detectados (solo reglas)",
        "cat": "Precisión de categoría, todos los tickets",
        "urg": "Precisión de urgencia, todos los tickets",
        "urgent_all": "Urgentes detectados (proceso completo)",
        "review": "Enviados a revisión (sin decidir)",
        "misses": "No acertados",
        "expected": "esperado",
        "got": "obtenido",
        "by": {"rule": "regla", "ai": "IA", "fallback": "sin decidir"},
        "no_misses": "  ninguno",
        "need_key": "--live necesita una clave de API. Agrega ANTHROPIC_API_KEY a tu archivo .env, o ejecútalo sin --live.",
        "missing": "No se encontró el archivo de prueba: {path}. Créalo con: python scripts/make_tickets.py --seed 42",
        "not_labeled": "{path} no tiene las columnas expected_category / expected_urgency, así que no hay con qué comparar. "
                       "Usa un archivo etiquetado como data/test_labeled.csv.",
    },
}


class NoAIClient:
    """Rules-only mode: every AI call 'fails', so only rule decisions count."""

    def complete(self, request):
        raise AIError("no_fixture")


def ratio(part, whole):
    pct = 100 * part / whole if whole else 0
    return f"{part}/{whole} ({pct:.1f}%)"


def evaluate(rows, client, lang, model):
    """Triage each labeled row and return (metrics dict, list of misses)."""
    results = [triage_ticket(row, client, lang, model) for row in rows]
    pairs = list(zip(rows, results))
    by_rule = [(row, res) for row, res in pairs if res["decided_by"] == "rule"]
    urgent = [(row, res) for row, res in pairs if row["expected_urgency"] == "urgent"]
    m = {
        "tickets": len(rows),
        "rule_decided": len(by_rule),
        "rule_cat_ok": sum(row["expected_category"] == res["category"] for row, res in by_rule),
        "rule_urg_ok": sum(row["expected_urgency"] == res["urgency"] for row, res in by_rule),
        "urgent_total": len(urgent),
        "urgent_by_rules": sum(res["urgency"] == "urgent" and res["decided_by"] == "rule"
                               for _, res in urgent),
        "urgent_found": sum(res["urgency"] == "urgent" for _, res in urgent),
        "cat_ok": sum(row["expected_category"] == res["category"] for row, res in pairs),
        "urg_ok": sum(row["expected_urgency"] == res["urgency"] for row, res in pairs),
        "fallback": sum(res["decided_by"] == "fallback" for _, res in pairs),
    }
    return m, pairs


def print_report(m, pairs, lang, live, model):
    x = TEXT[lang]
    print(x["label"])
    print(x["live_mode"].format(model=model) if live else x["rules_mode"])
    print()
    lines = [(x["tickets"], str(m["tickets"])),
             (x["coverage"], ratio(m["rule_decided"], m["tickets"])),
             (x["rule_cat"], ratio(m["rule_cat_ok"], m["rule_decided"])),
             (x["rule_urg"], ratio(m["rule_urg_ok"], m["rule_decided"])),
             (x["urgent_rules"], ratio(m["urgent_by_rules"], m["urgent_total"]))]
    if live:
        lines += [(x["cat"], ratio(m["cat_ok"], m["tickets"])),
                  (x["urg"], ratio(m["urg_ok"], m["tickets"])),
                  (x["urgent_all"], ratio(m["urgent_found"], m["urgent_total"])),
                  (x["review"], ratio(m["fallback"], m["tickets"]))]
    for name, value in lines:
        print(f"  {name:<45} {value}")

    # Misses: wrong decisions, plus urgent tickets that were not marked urgent.
    # In rules-only mode, tickets left for the AI are not counted as wrong.
    misses = []
    for row, res in pairs:
        scored = live or res["decided_by"] == "rule"
        wrong = scored and (row["expected_category"] != res["category"]
                            or row["expected_urgency"] != res["urgency"])
        missed_urgent = row["expected_urgency"] == "urgent" and res["urgency"] != "urgent"
        if wrong or missed_urgent:
            misses.append((row, res))
    print()
    print(f'{x["misses"]} ({len(misses)})')
    for row, res in misses:
        print(f'  {row["ticket_id"]}  {x["expected"]}: {row["expected_category"]}/{row["expected_urgency"]}'
              f'  {x["got"]}: {res["category"] or "-"}/{res["urgency"]} ({x["by"][res["decided_by"]]})')
        print(f'        {res["body"][:90]}')
    if not misses:
        print(x["no_misses"])


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    load_dotenv(config.PROJECT_DIR / ".env")
    parser = argparse.ArgumentParser(description="Evaluate triage on synthetic labeled tickets (Puentara is fictional).")
    parser.add_argument("--data", type=Path, default=config.DEFAULT_TEST_FILE)
    parser.add_argument("--live", action="store_true", help="use Claude for the full pipeline (needs a key)")
    parser.add_argument("--summary-lang", choices=["en", "es"], default="en")
    args = parser.parse_args(argv)
    lang = args.summary_lang

    if not args.data.is_file():
        print(TEXT[lang]["missing"].format(path=args.data), file=sys.stderr)
        return 2
    with open(args.data, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    needed = {"ticket_id", "body", "expected_category", "expected_urgency"}
    if not needed <= set(reader.fieldnames or []):
        print(TEXT[lang]["not_labeled"].format(path=args.data), file=sys.stderr)
        return 2

    model = os.getenv("ANTHROPIC_MODEL", "").strip() or config.DEFAULT_MODEL
    if args.live:
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key or api_key == "your-key-here":
            print(TEXT[lang]["need_key"], file=sys.stderr)
            return 2
        client = LiveClient(api_key, model)
    else:
        client = NoAIClient()
    try:
        metrics, pairs = evaluate(rows, client, lang, model)
    except AIError as error:  # fatal only: bad key or unknown model
        print(t(lang, "fatal_ai").format(error=t(lang, "ai_problems").get(error.code, error.code)),
              file=sys.stderr)
        return 1
    print_report(metrics, pairs, lang, args.live, model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
