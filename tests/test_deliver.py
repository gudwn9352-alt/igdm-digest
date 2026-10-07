from pathlib import Path

import pytest

from igdm_digest.deliver import DeliveryError, deliver_report, send_gmail


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.actions = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        self.actions.append("ehlo")

    def starttls(self):
        self.actions.append("starttls")

    def login(self, user, password):
        self.actions.append(("login", user, password))

    def send_message(self, msg):
        FakeSMTP.sent.append((self.host, self.port, self.actions[:], msg))


def test_gmail_requires_app_password(cfg, monkeypatch):
    cfg["delivery"]["method"] = "gmail"
    cfg["delivery"]["gmail"].update({"from": "me@gmail.com", "to": "me@gmail.com"})
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    with pytest.raises(DeliveryError, match="GMAIL_APP_PASSWORD"):
        send_gmail(cfg, to="me@gmail.com", subject="s", text="t")


def test_gmail_sends_multipart_with_attachment(cfg, monkeypatch, tmp_path: Path):
    cfg["delivery"]["method"] = "gmail"
    cfg["delivery"]["gmail"].update({"from": "me@gmail.com", "to": "other@gmail.com"})
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    att = tmp_path / "x.md"
    att.write_text("# 첨부", encoding="utf-8")
    FakeSMTP.sent.clear()
    out = deliver_report(cfg, subject="제목", markdown="# 본문", html="<h1>본문</h1>", attachments=[att], smtp_factory=FakeSMTP)
    assert "other@gmail.com" in out
    host, port, actions, msg = FakeSMTP.sent[0]
    assert (host, port) == ("smtp.gmail.com", 587)
    assert actions == ["ehlo", "starttls", ("login", "me@gmail.com", "abcdefghijklmnop")]
    assert msg["Subject"] == "제목" and msg["To"] == "other@gmail.com"
    parts = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in parts and "text/html" in parts and "text/markdown" in parts


def test_file_and_stdout_delivery(cfg, capsys):
    out = deliver_report(cfg, subject="s", markdown="# 리포트", html="<p>x</p>")
    assert "파일 저장" in out
    md_files = list(Path(cfg["delivery"]["file"]["dir"]).glob("digest-*.md"))
    assert len(md_files) == 1 and md_files[0].read_text(encoding="utf-8") == "# 리포트"
    cfg["delivery"]["method"] = "stdout"
    assert deliver_report(cfg, subject="s", markdown="# 콘솔", html="") == "표준출력으로 출력"
    assert "# 콘솔" in capsys.readouterr().out
    cfg["delivery"]["method"] = "pigeon"
    with pytest.raises(DeliveryError):
        deliver_report(cfg, subject="s", markdown="", html="")
