# Investor Tracker mit Telegram – Einrichtung

Dieser Fork von [roreyshen/investor-tracker](https://github.com/roreyshen/investor-tracker)
meldet neue Insider-Trades (SEC Form 4 / Form 144 / 13F) und Trades von
US-Kongressmitgliedern (Repräsentantenhaus und Senat, STOCK Act) per **Telegram**.
Er läuft kostenlos alle ca. 15–30 Minuten in GitHub Actions, ganz ohne eigenen Server.

## Was gegenüber dem Original geändert ist

| Datei | Änderung |
|---|---|
| `src/notify/telegram.py` | **neu**: Telegram-Kanal mit deutschen Meldungen |
| `src/main.py` | Telegram als Kanal eingebunden |
| `.github/workflows/track.yml` | Telegram-Secrets, Test-Schalter `telegram_test`, Twilio entfernt |
| `config/settings.yml` | Telegram an; Telefonnummer und E-Mail des Autors entfernt; Mac-Agent aus |
| `scripts/import_bulk.py` | E-Mail des Autors durch `SEC_USER_AGENT` ersetzt |
| `state/seen.json` | zurückgesetzt (frischer Start) |

Entfernt wurden außerdem: der Mac-Agent, das Vercel-Dashboard (`site.yml`), die
Paper-Trading-Digests (`smg.yml`) und die Testdaten des Autors.

## 1. Telegram-Bot anlegen (5 Minuten)

1. In Telegram **@BotFather** öffnen und `/newbot` senden. Namen vergeben.
   Du bekommst ein **Token** wie `123456789:AA...`.
2. Deinem neuen Bot einmal irgendeine Nachricht schicken (z. B. „hallo“).
3. Im Browser öffnen: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Dort steht `"chat":{"id":123456789,...}`. Diese Zahl ist deine **Chat-ID**.
   Für eine Gruppe den Bot in die Gruppe holen; Gruppen-IDs sind negativ.
   Mehrere Empfänger: IDs mit Komma trennen.

## 2. Fork

Erledigt: `kannstemalsehn/investor-tracker`, mit allen Änderungen oben. Der Fork ist
öffentlich, das ist in Ordnung: Tokens liegen als Secrets und sind nicht sichtbar, und
GitHub Actions ist für öffentliche Repos unbegrenzt kostenlos.

Hinweis: Das Original hat **keine Lizenzdatei**. Forken und privat nutzen ist über die
GitHub-Nutzungsbedingungen gedeckt, den Code als eigenes Projekt neu veröffentlichen nicht.

## 3. Secrets eintragen

<https://github.com/kannstemalsehn/investor-tracker/settings/secrets/actions> öffnen (Settings → Secrets and variables → Actions) und je Eintrag **New repository secret** klicken:

| Name | Wert | Pflicht |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token von @BotFather | ja |
| `TELEGRAM_CHAT_ID` | deine Chat-ID (mehrere mit Komma) | ja |
| `SEC_USER_AGENT` | `Vorname Nachname deine@mail.de` | **ja**, die SEC sperrt Anfragen ohne echte Kontaktangabe |
| `DISCORD_WEBHOOK_URL` | Discord-Webhook | optional |
| `NTFY_TOPIC` | geheimer ntfy-Kanalname | optional |

## 4. Actions aktivieren und testen

1. Reiter **Actions** → „I understand my workflows, go ahead and enable them“.
   In Forks sind geplante Workflows sonst abgeschaltet.
2. Links **Track trades** → **Run workflow** → Haken bei **telegram_test** → **Run**.
   Nach ca. 1 Minute sollte die Testnachricht in Telegram ankommen.
3. Noch einmal **Run workflow** ohne Haken starten. Das ist der Kaltstart: Alle
   bereits vorhandenen Meldungen werden als „gesehen“ markiert, **ohne** Nachricht.
   Ab dann kommt jeder neue Treffer automatisch.

Wer ältere Treffer sehen will: **Run workflow** mit `backfill` = z. B. `5`
(holt die letzten 5 Tage Form-4-Meldungen nach; vorher besser mit `dry_run` testen).

## 5. Anpassen

**Wer immer gemeldet wird** steht in `config/watchlist.yml` (Abschnitte `congress` und
`insiders`). Die Liste stammt vom Autor. Namen eintragen oder streichen, committen, fertig.

**Schwellen** in `config/settings.yml` unter `filters`:

| Einstellung | Standard | Bedeutung |
|---|---|---|
| `min_insider_buy_usd` | 1.000.000 | Insider-Kauf durch Nicht-Watchlist-Person |
| `min_senior_buy_usd` | 250.000 | Kauf durch CEO/CFO/Präsident usw. |
| `min_insider_sell_usd` | 10.000.000 | Insider-Verkauf |
| `min_form144_usd` | 5.000.000 | angekündigter Insider-Verkauf |
| `min_congress_usd` | 50.000 | Kongress-Trade (Untergrenze der Spanne) |
| `cluster_min_insiders` | 3 | so viele Insider kaufen dieselbe Aktie … |
| `cluster_window_days` | 7 | … innerhalb so vieler Tage → immer Meldung |

Bei zu vielen Nachrichten die Schwellen erhöhen, bei zu wenigen senken. Unter `sources`
lassen sich einzelne Quellen abschalten (z. B. `edgar_13f: false`).

## Was die Meldungen leisten und was nicht

- **Form 4** kommt mit genauen Zahlen (Stückzahl × Preis = Volumen), meist 1–2 Werktage
  nach dem Trade. Das ist das zeitnahe Signal.
- **Kongress** liefert nur Betragsspannen und kommt gesetzlich bis zu 45 Tage verspätet.
  Jede Meldung zeigt den Verzug an.
- Papier-Meldungen (gescannte PDFs) kommen nur als Hinweis mit Link, ohne Details.
- GitHub startet geplante Läufe oft mit Verzögerung; realistisch alle 15–30 Minuten.
- Keine Anlageberatung. Ob die Signale nach Kosten eine Überrendite bringen, ist offen.

## Updates vom Original

Nicht blind auf **Sync fork** klicken: Der Bot des Autors committet ständig seinen
eigenen `state/seen.json`, das gibt Konflikte mit deinem Stand. Wenn du Updates willst,
einzelne Dateien in `src/` gezielt übernehmen.
