"""Password reset delivery. Development mode writes mail locally, never to an API."""

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4


class PasswordMailer:
    def __init__(self, config):
        self.config = config
        self.mode = "smtp" if config.get("SMTP_HOST") else "local"

    def send_reset(self, email, token):
        url = self.config["PUBLIC_ORIGIN"] + "/?" + urlencode({"reset_token": token})
        message = EmailMessage()
        message["Subject"] = "[CareerLens 교육용 프로젝트] 비밀번호 재설정"
        message["From"] = self.config.get("SMTP_FROM") or "no-reply@careerlens.local"
        message["To"] = email
        message.set_content(
            "CareerLens 로컬 교육용 프로젝트에서 요청한 비밀번호 재설정입니다.\n"
            "다음 링크는 15분 동안 한 번만 사용할 수 있습니다.\n\n"
            f"{url}\n\n요청하지 않았다면 이 메시지를 무시해 주세요.\n"
        )
        if self.mode == "local":
            folder = Path(self.config["MAIL_OUTBOX"])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"reset-{uuid4().hex}.eml").write_bytes(message.as_bytes())
            return
        host = self.config["SMTP_HOST"]
        port = int(self.config.get("SMTP_PORT") or 587)
        context = ssl.create_default_context()
        transport = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        options = {"context": context} if port == 465 else {}
        with transport(host, port, timeout=15, **options) as server:
            if port != 465:
                server.starttls(context=context)
            if self.config.get("SMTP_USERNAME"):
                server.login(self.config["SMTP_USERNAME"], self.config.get("SMTP_PASSWORD", ""))
            server.send_message(message)
