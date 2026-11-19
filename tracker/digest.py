"""Render the daily digest as one self-contained HTML page (also used as the email body)."""
from __future__ import annotations

import html
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from .models import Auction

PACIFIC = ZoneInfo("America/Los_Angeles")
SOURCE_NAMES = {"storagetreasures": "StorageTreasures", "bid13": "Bid13"}


def _ends(a: Auction) -> str:
    if not a.ends_at:
        return "?"
    return a.ends_at.astimezone(PACIFIC).strftime("%a %b %-d, %-I:%M %p")


def _row(a: Auction, new_keys: set[str]) -> str:
    e = html.escape
    badges = ""
    if a.key in new_keys:
        badges += '<span style="background:#1f7a3a;color:#fff;border-radius:3px;padding:0 4px;font-size:11px">NEW</span> '
    for t in a.tags:
        badges += f'<span style="background:#eef;border-radius:3px;padding:0 4px;font-size:11px">{e(t)}</span> '
    bid = f"${a.current_bid:,.0f}" if a.current_bid is not None else ""
    return (
        "<tr>"
        f'<td style="padding:6px;white-space:nowrap">{_ends(a)}</td>'
        f'<td style="padding:6px;text-align:right">{a.distance_mi:.0f} mi</td>'
        f'<td style="padding:6px"><a href="{e(a.url)}">{e(a.facility)}</a><br>'
        f'<span style="color:#666;font-size:12px">{e(a.city)} · {e(SOURCE_NAMES.get(a.source, a.source))}</span></td>'
        f'<td style="padding:6px">{e(a.unit_size or "")}</td>'
        f'<td style="padding:6px">{badges}{e(a.contents or "")}</td>'
        f'<td style="padding:6px;text-align:right">{bid}</td>'
        "</tr>"
    )


def _table(rows: list[Auction], new_keys: set[str], limit: int | None = None) -> str:
    if not rows:
        return '<p style="color:#666">None right now.</p>'
    more = ""
    if limit is not None and len(rows) > limit:
        more = f'<p style="color:#666">…and {len(rows) - limit} more. See the full digest page.</p>'
        rows = rows[:limit]
    head = "".join(
        f'<th style="padding:6px;text-align:left;border-bottom:2px solid #ccc">{h}</th>'
        for h in ["Ends (Pacific)", "Dist", "Facility", "Size", "Contents", "Bid"]
    )
    body = "".join(_row(a, new_keys) for a in rows)
    return f'<table style="border-collapse:collapse;width:100%;font-size:14px"><tr>{head}</tr>{body}</table>{more}'


def render(nearby: list[Auction], new: list[Auction], cfg: dict, errors: list[str],
           now: datetime | None = None, for_email: bool = False) -> str:
    """Full page lists every open auction; the email version keeps only new and ending-soon."""
    now = now or datetime.now(timezone.utc)
    far = datetime.max.replace(tzinfo=timezone.utc)
    by_end = sorted(nearby, key=lambda a: a.ends_at or far)
    live = [a for a in by_end if not a.ends_at or a.ends_at > now]
    soon = [a for a in live if a.ends_at and a.ends_at <= now + timedelta(hours=48)]
    new_keys = {a.key for a in new}
    new_live = [a for a in live if a.key in new_keys]
    counts = {}
    for a in live:
        counts[a.source] = counts.get(a.source, 0) + 1
    count_txt = ", ".join(f"{SOURCE_NAMES.get(s, s)}: {n}" for s, n in sorted(counts.items())) or "none"
    err_html = ""
    if errors:
        items = "".join(f"<li>{html.escape(x)}</li>" for x in errors)
        err_html = f'<div style="background:#fff3cd;padding:8px;margin:12px 0"><b>Some sources failed this run:</b><ul>{items}</ul></div>'

    stamp = now.astimezone(PACIFIC).strftime("%A %B %-d, %Y at %-I:%M %p")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Storage auctions near {cfg['home_zip']}</title></head>
<body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:0 auto;padding:16px;color:#222;background:#fff">
<h1 style="margin-bottom:4px">Storage auctions within {cfg['radius_miles']} mi of {cfg['home_zip']}</h1>
<p style="color:#666;margin-top:0">Updated {stamp}. {len(live)} open auctions ({count_txt}). {len(new_live)} new since last run.</p>
{err_html}
<h2>New since last run ({len(new_live)})</h2>
{_table(new_live, new_keys, limit=150 if for_email else None)}
<h2>Ending in the next 48 hours ({len(soon)})</h2>
{_table(soon, new_keys, limit=150 if for_email else None)}
{"" if for_email else f"<h2>All open auctions ({len(live)})</h2>" + _table(live, new_keys)}
<p style="color:#999;font-size:12px;margin-top:24px">Distances are straight-line from the facility's ZIP (Bid13) or city center (StorageTreasures).
Always confirm details on the auction page before bidding.</p>
</body></html>"""


def send_email(html_body: str, subject: str) -> bool:
    """Send via SMTP if SMTP_USER/SMTP_PASSWORD/DIGEST_TO are set. Returns True if sent."""
    user, pw, to = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"), os.getenv("DIGEST_TO")
    if not (user and pw and to):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content("Your storage auction digest is attached as HTML. Open it in an HTML-capable mail client.")
    msg.add_alternative(html_body, subtype="html")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, pw)
        s.send_message(msg)
    return True
