"""End-to-end runs of triage.py and evaluate.py in demo mode, plus bilingual output."""

import csv
import re

import pytest

import config
import evaluate
import triage
from helpers import FakeAI, ai_answer
from ticket_triage.route import triage_ticket
from ticket_triage.strings import STRINGS

SAMPLE = str(config.PROJECT_DIR / "data" / "sample_tickets.csv")


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    # Ignore any real .env on this machine: tests must never call the API.
    monkeypatch.setattr(triage, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(evaluate, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def read_output(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_demo_run_writes_csv_and_summary(tmp_path, capsys):
    out = tmp_path / "new_folder" / "triaged.csv"
    assert triage.main([SAMPLE, "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("Demo mode: no API key found")
    assert "Puentara (fictional company)" in printed
    assert "URGENT" in printed

    rows = read_output(out)
    assert len(rows) == 30
    assert out.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM, so Excel shows accents
    for row in rows:
        assert row["decided_by"] in {"rule", "ai", "fallback"}
        assert row["needs_human"] in {"true", "false"}
        # no card numbers or codes in the output file
        assert not re.search(r"\d{6,}", row["body"].replace(" ", "").replace("-", ""))


def test_demo_run_in_spanish(tmp_path, capsys):
    out = tmp_path / "triaged.csv"
    assert triage.main([SAMPLE, "--out", str(out), "--summary-lang", "es"]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("Modo demo: no se encontró una clave de API")
    assert "URGENTES - atiéndelos primero" in printed
    assert "Tarjeta perdida o robada" in printed
    rows = read_output(out)
    reasons = " ".join(r["reason"] for r in rows)
    assert "Reporta una tarjeta perdida o robada" in reasons


@pytest.mark.parametrize("text,expected", [
    ("Me robaron la tarjeta, ¿qué hago?", "es"),
    ("My card was stolen, what do I do?", "en"),
])
def test_language_column_follows_the_customer(text, expected):
    result = triage_ticket({"ticket_id": "X", "subject": "", "body": text}, FakeAI(ai_answer()), "en")
    assert result["language"] == expected


@pytest.mark.parametrize("lang,expected", [
    ("en", "Card reported lost or stolen"),
    ("es", "Reporta una tarjeta perdida o robada"),
])
def test_reasons_follow_summary_language(lang, expected):
    result = triage_ticket({"ticket_id": "X", "subject": "", "body": "Me robaron la tarjeta"},
                           FakeAI(ai_answer()), lang)
    assert result["reason"].startswith(expected)


def test_both_languages_have_the_same_strings():
    def keys(d, prefix=""):
        out = set()
        for k, v in d.items():
            out.add(prefix + k)
            if isinstance(v, dict):
                out |= keys(v, prefix + k + ".")
        return out
    assert keys(STRINGS["en"]) == keys(STRINGS["es"])


def test_zendesk_style_headers(tmp_path):
    src = tmp_path / "export.csv"
    src.write_text("Id,Subject,Description,Created at,Via\n"
                   "101,Ayuda,Perdí mi tarjeta ayer,2026-10-01,email\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    assert triage.main([str(src), "--out", str(out)]) == 0
    row = read_output(out)[0]
    assert row["Id"] == "101"
    assert row["category"] == "card_lost_stolen"
    assert row["queue"] == "fraud_security"


def test_missing_file_gives_clear_message(capsys):
    assert triage.main(["nope.csv"]) == 2
    assert "Input file not found" in capsys.readouterr().err


def test_missing_body_column(tmp_path, capsys):
    src = tmp_path / "bad.csv"
    src.write_text("ticket_id,notes\n1,hello\n", encoding="utf-8")
    assert triage.main([str(src), "--summary-lang", "es"]) == 2
    assert "no tiene la columna 'body'" in capsys.readouterr().err


def test_live_without_key_explains_what_to_do(capsys):
    assert triage.main([SAMPLE, "--live"]) == 2
    assert "Add ANTHROPIC_API_KEY to .env" in capsys.readouterr().err


def test_record_needs_live(capsys):
    assert triage.main([SAMPLE, "--record"]) == 2
    assert "--record only works with --live" in capsys.readouterr().err


def test_evaluate_demo_reports_rules_layer_only(capsys):
    assert evaluate.main([]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("Synthetic sample data")
    assert "rules layer only" in printed
    assert "Rules coverage" in printed
    assert "all tickets" not in printed  # no full-pipeline numbers in demo mode


def test_evaluate_live_without_key(capsys):
    assert evaluate.main(["--live", "--summary-lang", "es"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_evaluate_full_pipeline_with_fake_client():
    rows = [
        {"ticket_id": "1", "subject": "", "body": "Card stolen",
         "expected_category": "card_lost_stolen", "expected_urgency": "urgent"},
        {"ticket_id": "2", "subject": "", "body": "Do you have a plan for teams?",
         "expected_category": "general_question", "expected_urgency": "low"},
    ]
    metrics, _ = evaluate.evaluate(rows, FakeAI(ai_answer("general_question", "low")), "en", "m")
    assert metrics["rule_decided"] == 1
    assert metrics["cat_ok"] == 2
    assert metrics["urgent_found"] == 1


def test_live_record_path_with_fake_client(tmp_path, monkeypatch, capsys):
    """--live --record end to end, with a fake SDK instead of the network."""
    import json
    from types import SimpleNamespace

    from ticket_triage.ai import LiveClient

    reply = json.dumps(ai_answer("general_question", "low", reason="Pregunta general"))
    fake_sdk = SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(type="text", text=reply)])))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(triage, "LiveClient",
                        lambda key, model: LiveClient(key, model, sdk_client=fake_sdk))
    fixtures = tmp_path / "fx.json"
    out = tmp_path / "out.csv"
    code = triage.main([SAMPLE, "--out", str(out), "--live", "--record",
                        "--fixtures", str(fixtures), "--summary-lang", "es"])
    assert code == 0
    printed = capsys.readouterr().out
    assert printed.startswith("Modo en vivo")
    saved = json.loads(fixtures.read_text(encoding="utf-8"))["responses"]
    entries = [by_lang["es"] for by_lang in saved.values()]
    assert entries and all(e["source"] == "recorded" for e in entries)
    assert any(r["decided_by"] == "ai" for r in read_output(out))


def test_reads_excel_cp1252_csv(tmp_path):
    src = tmp_path / "excel.csv"
    src.write_bytes("ticket_id,subject,body\n1,Ayuda,Perdí mi tarjeta en el baño\n".encode("cp1252"))
    out = tmp_path / "out.csv"
    assert triage.main([str(src), "--out", str(out)]) == 0
    row = read_output(out)[0]
    assert row["body"] == "Perdí mi tarjeta en el baño"
    assert row["queue"] == "fraud_security"


@pytest.mark.parametrize("lang,expected", [("en", "is a folder, not a CSV file"),
                                           ("es", "es una carpeta, no un archivo CSV")])
def test_folder_instead_of_file(tmp_path, capsys, lang, expected):
    assert triage.main([str(tmp_path), "--summary-lang", lang]) == 2
    captured = capsys.readouterr()
    assert expected in captured.err
    assert captured.out == ""  # no demo-mode line before the error


@pytest.mark.parametrize("lang,expected", [("en", "has no expected_category"),
                                           ("es", "no tiene las columnas expected_category")])
def test_evaluate_needs_a_labeled_file(capsys, lang, expected):
    assert evaluate.main(["--data", SAMPLE, "--summary-lang", lang]) == 2
    assert expected in capsys.readouterr().err


@pytest.mark.parametrize("lang,expected", [
    ("en", "Row 2 of"),
    ("es", "La fila 2 de"),
])
def test_ragged_row_gives_clear_message(tmp_path, capsys, lang, expected):
    src = tmp_path / "ragged.csv"
    src.write_text("ticket_id,body\nX1,hello,extra\n", encoding="utf-8")
    assert triage.main([str(src), "--out", str(tmp_path / "o.csv"), "--summary-lang", lang]) == 2
    err = capsys.readouterr().err
    assert expected in err
    assert ("quotes" in err) if lang == "en" else ("comillas" in err)
