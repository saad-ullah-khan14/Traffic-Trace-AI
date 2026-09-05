"""Officer PIN gate.

Threat model is deliberately small: this stops someone walking up to an
unattended laptop during a demo and confirming matches or wiping the database.
It is not protection against a network attacker, and it is not pretending to be.

The PIN guards the two things that actually change or destroy state — match
decisions and the demo reset. Read-only pages are left open so the feed and map
can be shown on a projector without typing a PIN first.
"""

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_pin(x_officer_pin: Annotated[str | None, Header(alias="X-Officer-Pin")] = None) -> None:
    if not x_officer_pin:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Officer PIN required")

    # compare_digest, not ==, so a wrong PIN cannot be found one character at a
    # time by timing the response.
    if not hmac.compare_digest(x_officer_pin, settings.OFFICER_PIN):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect PIN")
