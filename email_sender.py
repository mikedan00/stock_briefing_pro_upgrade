
"""
email_sender.py — Gmail SMTP 발송. 표준 smtplib 사용.
"""
from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from datetime import date

from config import GMAIL_USER, GMAIL_APP_PASSWORD

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match((addr or "").strip()))


def report_to_html(report_text: str) -> str:
    lines = []
    for raw in report_text.splitlines():
        s = raw.strip()
        if not s:
            lines.append("<br>")
        elif s.startswith("#") or s.startswith("【"):
            lines.append(f"<h2>{escape(s.strip('# '))}</h2>")
        elif s.startswith("-"):
            lines.append(f"<p>• {escape(s.lstrip('- '))}</p>")
        else:
            lines.append(f"<p>{escape(s)}</p>")
    return "<html><body style='font-family:Malgun Gothic,Arial;line-height:1.65;'>" + "\n".join(lines) + "</body></html>"


def send_report_email(to_address: str, report_text: str, gmail_user: str = "", gmail_password: str = "", attachments: list[tuple[str, bytes, str]] | None = None) -> tuple[bool, str]:
    sender = gmail_user or GMAIL_USER
    password = gmail_password or GMAIL_APP_PASSWORD
    if not sender or not password:
        return False, "Gmail 계정 정보가 설정되지 않았습니다."
    if not valid_email(to_address):
        return False, "유효하지 않은 수신 이메일 주소입니다."
    today = date.today().isoformat()
    msg = EmailMessage()
    msg["Subject"] = f"📊 주식 AI 브리핑 리포트 [{today}]"
    msg["From"] = formataddr(("AI Stock Briefing", sender))
    msg["To"] = to_address
    msg.set_content(report_text)
    msg.add_alternative(report_to_html(report_text), subtype="html")
    for filename, data, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(sender, password)
            server.send_message(msg)
        return True, f"✅ 리포트가 {to_address}로 발송되었습니다."
    except smtplib.SMTPAuthenticationError:
        return False, "❌ Gmail 인증 실패. 앱 비밀번호와 2단계 인증을 확인하세요."
    except Exception as e:
        return False, f"❌ 이메일 발송 실패: {type(e).__name__}: {e}"
