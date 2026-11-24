from email.message import MIMEPart
from email.utils import make_msgid
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .constants import EMAIL_REVIEW_LINE, EMAIL_TAGLINE

LOGO_PNG = (Path(__file__).parent / "assets" / "eventra-logo-on-ink.png").read_bytes()


def build_email(
    to: str,
    subject: str,
    *,
    headline: str,
    paragraphs: list[str],
    reason: str,
    turn: str = "",
    pill: str = "",
    ticket: dict | None = None,
    button: tuple[str, str] | None = None,
    link: tuple[str, str] | None = None,
    after: str = "",
    account_link: bool = True,
    review_line: bool = True,
) -> EmailMultiAlternatives:
    logo_cid = make_msgid(domain="eventra")
    context = {
        "logo_cid": logo_cid[1:-1],
        "subject": subject,
        "headline": headline,
        "turn": turn,
        "pill": pill,
        "paragraphs": paragraphs,
        "ticket": ticket,
        "button": button,
        "link": link,
        "after": after,
        "tagline": EMAIL_TAGLINE,
        "review_line": EMAIL_REVIEW_LINE if review_line else "",
        "reason": reason,
        "account_url": f"{settings.FRONTEND_URL}/profile" if account_link else "",
        "help_email": settings.EMAIL_REPLY_TO,
    }
    email = EmailMultiAlternatives(
        subject=subject,
        body=_plain_text(context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to],
        reply_to=[settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None,
    )
    email.attach_alternative(
        render_to_string("notifications/email.html", context), "text/html"
    )
    logo = MIMEPart()
    logo.set_content(
        LOGO_PNG, maintype="image", subtype="png", disposition="inline", cid=logo_cid
    )
    email.attach(logo)
    return email


def _plain_text(c: dict) -> str:
    blocks = [" ".join(filter(None, [c["headline"], c["turn"]])), *c["paragraphs"]]
    if c["ticket"]:
        t = c["ticket"]
        blocks.append(
            "\n".join(
                [t["title"], *t.get("lines", ())]
                + [f"{label}: {value}" for label, value in t.get("rows", ())]
            )
        )
    for action in (c["button"], c["link"]):
        if action:
            blocks.append(f"{action[0]}: {action[1]}")
    if c["after"]:
        blocks.append(c["after"])
    footer = [c["tagline"]]
    if c["review_line"]:
        footer.append(c["review_line"])
    if c["help_email"]:
        footer.append(f"Questions? Write to {c['help_email']}.")
    footer.append(f"You're getting this because {c['reason']}.")
    if c["account_url"]:
        footer.append(f"Your account: {c['account_url']}")
    blocks.append("--\n" + "\n".join(footer))
    return "\n\n".join(blocks) + "\n"
