"""Redaction helpers for audit log params."""

from collections.abc import Callable, Mapping

RedactFn = Callable[[Mapping], dict]


def redact_card_number(params: Mapping) -> dict:
    out = dict(params)
    if "card_number" in out:
        cn = str(out["card_number"])
        out["card_number"] = f"****{cn[-4:]}" if len(cn) >= 4 else "****"
    return out


def redact_email(params: Mapping) -> dict:
    out = dict(params)
    if "email" in out and isinstance(out["email"], str):
        local, _, domain = out["email"].partition("@")
        out["email"] = f"{local[0]}***@{domain}" if local else out["email"]
    return out


def chain(*fns: RedactFn) -> RedactFn:
    def apply(params: Mapping) -> dict:
        out = dict(params)
        for fn in fns:
            out = fn(out)
        return out

    return apply


def _identity(p: Mapping) -> dict:
    return dict(p)


IDENTITY: RedactFn = _identity
