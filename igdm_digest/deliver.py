"""리포트 전달: Gmail(SMTP 앱 비밀번호) / 파일 / 표준출력. 아웃리치 메일 발송에도 같은 SMTP 설정을 쓴다."""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


class DeliveryError(RuntimeError):
    pass


def _gmail_settings(cfg: dict) -> dict:
    g = cfg["delivery"]["gmail"]
    env_name = g.get("app_password_env") or "GMAIL_APP_PASSWORD"
    password = (os.environ.get(env_name) or "").replace(" ", "")
    if not g.get("from"):
        raise DeliveryError("delivery.gmail.from 이 비어 있습니다 (보내는 Gmail 주소)")
    if not password:
        raise DeliveryError(
            f"환경변수 {env_name} 에 Gmail 앱 비밀번호가 없습니다. "
            "Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호에서 만든 16자리 값을 넣으세요."
        )
    return {
        "host": g.get("smtp_host") or "smtp.gmail.com",
        "port": int(g.get("smtp_port") or 587),
        "user": g["from"],
        "password": password,
        "to": g.get("to") or g["from"],
    }


def send_gmail(cfg: dict, *, to: str, subject: str, text: str, html: str | None = None, attachments: list[Path] | None = None, smtp_factory=None) -> str:
    s = _gmail_settings(cfg)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = s["user"]
    msg["To"] = to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or []:
        p = Path(path)
        if p.exists():
            msg.add_attachment(p.read_bytes(), maintype="text", subtype="markdown", filename=p.name)
    factory = smtp_factory or smtplib.SMTP
    with factory(s["host"], s["port"], timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(s["user"], s["password"])
        smtp.send_message(msg)
    return f"Gmail 발송 완료 → {to}"


def deliver_report(cfg: dict, *, subject: str, markdown: str, html: str, attachments: list[Path] | None = None, smtp_factory=None) -> str:
    method = (cfg["delivery"].get("method") or "stdout").lower()
    if method == "gmail":
        to = cfg["delivery"]["gmail"].get("to") or cfg["delivery"]["gmail"].get("from")
        return send_gmail(cfg, to=to, subject=subject, text=markdown, html=html, attachments=attachments, smtp_factory=smtp_factory)
    if method == "file":
        out_dir = Path(cfg["delivery"]["file"].get("dir") or "data/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        md_path = out_dir / f"digest-{stamp}.md"
        html_path = out_dir / f"digest-{stamp}.html"
        md_path.write_text(markdown, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
        return f"파일 저장 → {md_path} , {html_path}"
    if method == "stdout":
        print(markdown)
        return "표준출력으로 출력"
    raise DeliveryError(f"알 수 없는 delivery.method: {method} (gmail | file | stdout)")
