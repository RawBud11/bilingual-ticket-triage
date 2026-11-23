import re

import pytest

from ticket_triage.mask import CARD_MASK, CODE_MASK, mask_sensitive


@pytest.mark.parametrize("text", [
    "My card number is 0000123456789012, please block it.",
    "My card number is 0000 1234 5678 9012, please block it.",
    "Mi tarjeta es 0000-1234-5678-9012, bloquéenla por favor.",
])
def test_masks_card_numbers(text):
    masked, count = mask_sensitive(text)
    assert CARD_MASK in masked
    assert count == 1
    assert not re.search(r"\d{4}", masked)


@pytest.mark.parametrize("text,secret", [
    ("Someone used my card, CVV 123", "123"),
    ("el cvv: 4821 por si lo necesitas", "4821"),
    ("Mi código de seguridad es 907", "907"),
    ("I got a code 482913 I never asked for", "482913"),
    ("Me llegó el código 482913 por SMS", "482913"),
    ("el codigo que me llego es 553201", "553201"),
    ("my PIN is 1234", "1234"),
    ("OTP: 99210", "99210"),
])
def test_masks_cvv_and_codes(text, secret):
    masked, count = mask_sensitive(text)
    assert secret not in masked
    assert CODE_MASK in masked
    assert count == 1


def test_masks_card_and_cvv_together_en_es():
    en, n_en = mask_sensitive("My card is 0000 1043 3218 1960, CVV 529.")
    es, n_es = mask_sensitive("Mi tarjeta es 0000104332181960 y el CVV 529.")
    assert n_en == 2 and n_es == 2
    assert "529" not in en and "529" not in es


@pytest.mark.parametrize("text", [
    "I sent $139.85 on Oct 15 and it says failed.",
    "¿Dónde descargo mi formulario 1099 del 2025?",
    "My transfer of $1,250.00 is pending since 2026-10-03.",
    "Termina en 4821.",  # last 4 digits alone are fine to keep
])
def test_leaves_normal_numbers_alone(text):
    masked, count = mask_sensitive(text)
    assert masked == text
    assert count == 0


def test_empty_text():
    assert mask_sensitive("") == ("", 0)
    assert mask_sensitive(None) == ("", 0)


@pytest.mark.parametrize("text", [
    "card 0000.1111.2222.3333 not working",
    "mi tarjeta 0000.1111.2222.3333 no funciona",
])
def test_masks_card_numbers_with_dots(text):
    masked, count = mask_sensitive(text)
    assert CARD_MASK in masked and count == 1
    assert "1111" not in masked


@pytest.mark.parametrize("text,secret", [
    ("mi código es 123 456, no me deja entrar", "123 456"),
    ("el codigo: 123-456", "123-456"),
    ("my code is 123 456", "123 456"),
    ("verification code 1234-5678", "1234-5678"),
])
def test_masks_codes_typed_in_two_groups(text, secret):
    masked, count = mask_sensitive(text)
    assert secret not in masked
    assert CODE_MASK in masked and count == 1
