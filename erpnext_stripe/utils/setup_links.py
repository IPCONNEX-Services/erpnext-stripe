"""Signed, expiring links that let a customer add their own card.

Frappe v16 has no `frappe.utils.make_signed_url` / `verify_signed_url` — the
previous implementation called both, so every "Send Card Setup Link" raised
AttributeError. Tokens are built here from the same secret Frappe uses for its
own signed URLs (`frappe.utils.verified_command.get_secret`).

Token layout:  <base64url(payload json)>.<hex hmac-sha256 of that blob>
Payload:       {"sc": "<Stripe Customer docname>", "exp": <unix timestamp>}

The token carries its own expiry inside the signed blob, so there is nothing to
store and nothing to clean up. It stays usable until it expires — a customer who
mistypes their card can just click the link again.
"""

import base64
import hashlib
import hmac
import json
import time

import frappe
from frappe import _
from frappe.utils import get_url

# templates/pages/add_card.html is served at its file name, underscore and all.
# The old code linked to "/add-card", which 404s.
ADD_CARD_ROUTE = "/add_card"

DEFAULT_EXPIRY_SECONDS = 48 * 60 * 60


def _secret() -> bytes:
    from frappe.utils.verified_command import get_secret

    return frappe.safe_encode(get_secret())


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(blob: str) -> bytes:
    return base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4))


def _sign(blob: str) -> str:
    return hmac.new(_secret(), blob.encode(), hashlib.sha256).hexdigest()


def make_setup_token(stripe_customer: str, expires_in: int = DEFAULT_EXPIRY_SECONDS) -> str:
    """Return a signed token granting card-setup access to one Stripe Customer."""
    payload = {"sc": stripe_customer, "exp": int(time.time()) + int(expires_in)}
    blob = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{blob}.{_sign(blob)}"


def verify_setup_token(token: str) -> dict:
    """Return the payload of a valid token, or throw PermissionError.

    Every rejection path raises the same message so the page never reveals
    whether a Stripe Customer exists.
    """
    invalid = _("This card setup link has expired or is invalid. Please ask us for a new one.")

    if not token or "." not in token:
        frappe.throw(invalid, frappe.PermissionError)

    blob, _sep, given = token.partition(".")
    if not hmac.compare_digest(given, _sign(blob)):
        frappe.throw(invalid, frappe.PermissionError)

    try:
        payload = json.loads(_b64decode(blob))
    except Exception:
        frappe.throw(invalid, frappe.PermissionError)

    if not payload.get("sc") or int(payload.get("exp") or 0) < time.time():
        frappe.throw(invalid, frappe.PermissionError)

    return payload


def get_setup_url(stripe_customer: str, expires_in: int = DEFAULT_EXPIRY_SECONDS) -> str:
    """Full public URL a customer can open to add their own card."""
    token = make_setup_token(stripe_customer, expires_in)
    return get_url(f"{ADD_CARD_ROUTE}?token={token}")
