"""SendGrid transactional-email helper.

Reads `SENDGRID_API_KEY`, `SENDER_EMAIL`, `SENDER_NAME` from the environment
and exposes a single `send_html_email()` function used by the
`/api/offer-email/send` endpoint. Errors are surfaced as `EmailError`
exceptions with clear, operator-friendly messages.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

logger = logging.getLogger(__name__)


class EmailError(Exception):
    """Raised when an email cannot be sent. The message is safe to surface
    to the operator (does NOT contain API keys or internal stack traces)."""


def send_html_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    reply_to: Optional[str] = None,
) -> str:
    """Send `html_body` to `to_email` via SendGrid. Returns the SendGrid
    `x-message-id` header on success, raises `EmailError` on any failure."""

    api_key = os.environ.get("SENDGRID_API_KEY")
    sender  = os.environ.get("SENDER_EMAIL")
    name    = os.environ.get("SENDER_NAME") or "BluBridge HR"

    if not api_key:
        raise EmailError("SENDGRID_API_KEY is not configured on the server.")
    if not sender:
        raise EmailError(
            "SENDER_EMAIL is not configured. Set it to a SendGrid-verified "
            "single-sender address (Settings → Sender Authentication → Single "
            "Sender Verification) and restart the backend."
        )
    if not to_email or "@" not in to_email:
        raise EmailError(f"Invalid recipient email: {to_email!r}")

    message = Mail(
        from_email=Email(sender, name),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content("text/html", html_body),
    )
    if reply_to:
        message.reply_to = Email(reply_to)

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
    except Exception as e:  # network / SDK errors
        logger.exception("SendGrid SDK error")
        raise EmailError(f"SendGrid request failed: {e}") from e

    status = getattr(response, "status_code", None)
    if status != 202:
        # SendGrid returns the failure reason in the response body. Decode
        # it and surface so the operator can act (verified sender, paused
        # account, etc.).
        body = getattr(response, "body", b"")
        try:
            body_text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
        except Exception:
            body_text = "(unparseable body)"
        raise EmailError(
            f"SendGrid returned HTTP {status}. Common causes: sender "
            f"email not verified, API key revoked/insufficient scope, or "
            f"recipient blocked. Detail: {body_text[:400]}"
        )

    msg_id = ""
    try:
        msg_id = response.headers.get("X-Message-Id", "") if response.headers else ""
    except Exception:
        pass
    return msg_id
