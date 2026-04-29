import pytest

from gateway.audit.redaction import chain, redact_card_number, redact_email

pytestmark = pytest.mark.unit


def test_card_number_redacted():
    assert redact_card_number({"card_number": "4111111111111234"}) == {"card_number": "****1234"}


def test_email_redacted():
    assert redact_email({"email": "alice@example.com"})["email"] == "a***@example.com"


def test_chain():
    fn = chain(redact_card_number, redact_email)
    out = fn({"card_number": "4111111111111234", "email": "bob@x.com", "amount": 100})
    assert out["card_number"] == "****1234"
    assert out["email"] == "b***@x.com"
    assert out["amount"] == 100
