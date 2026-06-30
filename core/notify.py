"""Report delivery channels for the automated job.

Channels (configured in automation.json -> "notify"):
  macos  -> desktop notification (WORKS TODAY, no setup)        [default on]
  email  -> SMTP send (real; you provide host/user/pass/to)
  whatsapp -> STUB: needs a paid provider (Twilio/Meta Cloud API) + opt-in number

Nothing is sent unless the channel is enabled. Secrets come from config or env,
never hardcoded. Each sender fails soft and returns a status string.
"""
import os
import smtplib
import subprocess
from email.mime.text import MIMEText


def _macos(summary: str, body_path: str) -> str:
    title = "StockSense — Buy today"
    script = (f'display notification "{summary}" with title "{title}"')
    try:
        subprocess.run(["osascript", "-e", script], check=True,
                       capture_output=True, timeout=10)
        return "macos: notified"
    except Exception as e:
        return f"macos: failed ({e})"


def _email(cfg: dict, subject: str, body: str) -> str:
    host = cfg.get("host") or os.getenv("SMTP_HOST")
    port = int(cfg.get("port") or os.getenv("SMTP_PORT") or 587)
    user = cfg.get("user") or os.getenv("SMTP_USER")
    pwd = cfg.get("password") or os.getenv("SMTP_PASS")
    to = cfg.get("to") or os.getenv("SMTP_TO")
    if not (host and user and pwd and to):
        return "email: skipped (set host/user/password/to in automation.json)"
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.get("from", user)
    msg["To"] = to
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, pwd)
            s.sendmail(msg["From"], [x.strip() for x in to.split(",")],
                       msg.as_string())
        return f"email: sent to {to}"
    except Exception as e:
        return f"email: failed ({e})"


def _whatsapp(cfg: dict, body: str) -> str:
    # TODO(notify-whatsapp): integrate a provider, e.g. Twilio:
    #   POST https://api.twilio.com/.../Messages.json
    #   from=whatsapp:<biz>  to=whatsapp:<owner>  body=<summary>
    # Requires account SID/token + a WhatsApp-enabled number + recipient opt-in.
    raise NotImplementedError(
        "WhatsApp delivery needs a paid provider (Twilio/Meta) — not wired in v1.")


def send_report(result: dict, config: dict) -> list:
    """result = core.report.generate() output. Returns per-channel status lines."""
    notify = config.get("notify", {}) or {}
    text = result.get("text", "")
    buy_n = result.get("buy_count", 0)
    summary = (f"{buy_n} item(s) to buy today. See reports/buy_today.txt"
               if buy_n else "Nothing urgent to buy today.")
    out = []

    if notify.get("macos", {}).get("enabled", True):   # default on
        out.append(_macos(summary, result.get("files", [None])[0]))
    if notify.get("email", {}).get("enabled"):
        out.append(_email(notify["email"], "StockSense — Buy-today report", text))
    if notify.get("whatsapp", {}).get("enabled"):
        try:
            out.append(_whatsapp(notify["whatsapp"], summary))
        except NotImplementedError as e:
            out.append(f"whatsapp: {e}")
    return out
