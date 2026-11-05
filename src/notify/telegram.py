"""Telegram bot -- push to your phone, with full numbers and a link.

Uses the plain Bot API over HTTPS (no extra dependency). Needs two GitHub
secrets:

    TELEGRAM_BOT_TOKEN   from @BotFather
    TELEGRAM_CHAT_ID     your chat id (several allowed, comma-separated)

Test the setup without waiting for a real trade:

    python -m src.notify.telegram
"""
from __future__ import annotations

import html
import logging
import os
import sys
import time

import requests

from ..models import Trade
from .format import CODE_MEANING

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
# Telegram allows ~1 message/second per chat and ~20/minute in groups. A busy
# filing day is collapsed into individual messages plus one summary.
MAX_INDIVIDUAL = 15
PAUSE_SECONDS = 1.1
MAX_LEN = 4000           # hard limit is 4096

ACTION_DE = {"BUY": "KAUF", "SELL": "VERKAUF", "OTHER": "SONSTIGES"}
EMOJI = {"BUY": "\U0001F7E2", "SELL": "\U0001F534"}
SOURCE_DE = {
    "form4": "SEC Form 4 (Insider)",
    "form144": "SEC Form 144 (geplanter Insider-Verkauf)",
    "house": "Repräsentantenhaus (STOCK Act)",
    "senate": "Senat (STOCK Act)",
    "13f": "SEC 13F (Fonds-Bestand)",
}


def _e(value) -> str:
    """Escape for parse_mode=HTML. An unescaped '&' in a company name would
    make Telegram reject the whole message."""
    return html.escape(str(value), quote=False)


def _de_date(d) -> str:
    return d.strftime("%d.%m.%Y") if d else "?"


def _usd(v: float) -> str:
    """US-Dollar in deutscher Schreibweise: 1.234.567 $"""
    return f"{v:,.0f}".replace(",", ".") + " $"


def _price(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " $"


def format_message(t: Trade) -> str:
    action = ACTION_DE.get(t.action, t.action)
    head = f"{EMOJI.get(t.action, '⚪')} <b>{action}</b>"
    if t.ticker:
        head += f"  <code>{_e(t.ticker)}</code>"
    lines = [head]
    if t.company:
        lines.append(f"\U0001F3E2 {_e(t.company)}")

    who = f"\U0001F464 <b>{_e(t.person)}</b>"
    if t.role:
        who += f" · {_e(t.role)}"
    lines.append(who)
    lines.append("")

    if t.value_usd is not None:
        lines.append(f"\U0001F4B5 Volumen: <b>{_usd(t.value_usd)}</b>")
        if t.shares and t.price:
            lines.append(f"\U0001F4E6 {t.shares:,.0f}".replace(",", ".")
                         + f" Stück × {_price(t.price)}")
    elif t.value_range:
        lines.append(f"\U0001F4B5 Spanne: <b>{_e(t.value_range)}</b>")
    else:
        lines.append("\U0001F4B5 Betrag nicht angegeben")

    if t.code:
        meaning = CODE_MEANING.get(t.code, "")
        lines.append(f"\U0001F3F7 Code <code>{_e(t.code)}</code>"
                     + (f" ({_e(meaning)})" if meaning else ""))

    lines.append("")
    lines.append(f"\U0001F4C5 Gehandelt: {_de_date(t.trade_date)}"
                 f" · Gemeldet: {_de_date(t.filed_date)}")
    lag = t.lag_days
    if lag is not None and lag > 7:
        # A 40-day-old congressional trade must never read like breaking news.
        lines.append(f"⚠️ <b>{lag} Tage</b> zwischen Trade und Meldung")

    if t.reasons:
        lines.append("")
        lines.append("<b>Warum diese Meldung:</b>")
        lines += [f"• {_e(r)}" for r in t.reasons]
    if t.note:
        lines.append(f"\U0001F4DD {_e(t.note)}")

    lines.append("")
    lines.append(f"<i>Quelle: {_e(SOURCE_DE.get(t.source, t.source))}</i>")
    if t.url:
        lines.append(f'<a href="{_e(t.url)}">\U0001F4C4 Originalmeldung öffnen</a>')
    return "\n".join(lines)[:MAX_LEN]


def _chat_ids(raw: str) -> list[str]:
    return [c.strip() for c in (raw or "").split(",") if c.strip()]


def _post(token: str, chat_id: str, text: str, silent: bool = False,
          attempts: int = 3) -> bool:
    url = API.format(token=token, method="sendMessage")
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True,
               "disable_notification": silent}
    for n in range(attempts):
        try:
            r = requests.post(url, json=payload, timeout=20)
            if r.status_code == 429:
                # Telegram says exactly how long to back off.
                wait = 5
                try:
                    wait = r.json().get("parameters", {}).get("retry_after", 5)
                except ValueError:
                    pass
                log.warning("telegram rate limited, waiting %ss", wait)
                time.sleep(float(wait) + 0.5)
                continue
            if r.status_code == 400:
                # Usually malformed HTML; retry once as plain text so the
                # alert is not lost.
                log.error("telegram rejected message: %s", r.text[:300])
                payload.pop("parse_mode", None)
                payload["text"] = html.unescape(
                    text.replace("<b>", "").replace("</b>", "")
                        .replace("<i>", "").replace("</i>", "")
                        .replace("<code>", "").replace("</code>", ""))
                continue
            r.raise_for_status()
            return True
        except requests.RequestException as e:
            # The token is part of the URL -- never log the exception's URL.
            log.error("telegram post failed (attempt %d): %s",
                      n + 1, type(e).__name__)
            time.sleep(2 ** n)
    return False


def send(token: str, chat_ids_raw: str, trades: list[Trade],
         dry_run: bool = False) -> int:
    chats = _chat_ids(chat_ids_raw)
    if not token or not chats:
        log.warning("telegram: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing, skipping")
        return 0
    if not trades:
        return 0

    head, tail = trades[:MAX_INDIVIDUAL], trades[MAX_INDIVIDUAL:]
    sent = 0
    for t in head:
        text = format_message(t)
        # Watchlist hits are what you explicitly asked for, so they ring;
        # threshold-only hits arrive silently when many come at once.
        silent = len(trades) > 5 and not any("watchlist" in r for r in t.reasons)
        for chat in chats:
            if dry_run:
                log.info("[dry-run] telegram -> %s\n%s", chat, text)
                sent += 1
                continue
            if _post(token, chat, text, silent=silent):
                sent += 1
            time.sleep(PAUSE_SECONDS)

    if tail:
        summary = [f"➕ <b>{len(tail)} weitere Meldung(en)</b> in diesem Lauf:"]
        for t in tail[:40]:
            summary.append(f"• {ACTION_DE.get(t.action, t.action)} "
                           f"{_e(t.ticker or t.company[:25])} – {_e(t.amount_str)}"
                           f" – {_e(t.person)}")
        text = "\n".join(summary)[:MAX_LEN]
        for chat in chats:
            if dry_run:
                log.info("[dry-run] telegram summary -> %s", chat)
                sent += 1
            elif _post(token, chat, text):
                sent += 1

    log.info("telegram: sent %d message(s)", sent)
    return sent


def main() -> int:
    """Send one test message, so setup can be verified immediately."""
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chats = _chat_ids(os.environ.get("TELEGRAM_CHAT_ID", ""))
    if not token or not chats:
        print("TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID müssen gesetzt sein.")
        return 1
    ok = all(_post(token, c, "✅ <b>Investor Tracker</b>: Telegram ist "
                             "eingerichtet. Ab jetzt kommen hier die Meldungen.")
             for c in chats)
    print("Testnachricht gesendet." if ok else "Senden fehlgeschlagen, siehe Log.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
