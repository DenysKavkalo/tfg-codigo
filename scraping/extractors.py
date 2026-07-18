"""Detection helpers for blocked or challenged responses."""

from __future__ import annotations


BOT_CHALLENGE_PATTERNS = (
    "Bot or Not?",
    "Eres un robot",
    "DataDome CAPTCHA",
    "captcha-delivery.com",
    "arkoselabs",
    "g-recaptcha",
    "Access Denied",
    "challenge-container",
    "verify that you're not a robot",
    "window.awswafcookiedomainlist",
    "/__challenge_",
    "htlSpiderActionErrorCode",
)


def detect_bot_challenge(html: str) -> str | None:
    """Return the detected bot-challenge marker, if any."""
    lower = html.lower()
    for pattern in BOT_CHALLENGE_PATTERNS:
        if pattern.lower() in lower:
            return pattern
    return None
