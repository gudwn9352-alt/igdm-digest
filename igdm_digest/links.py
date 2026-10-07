"""DM 본문에서 링크를 뽑고, 링크 본문(텍스트)을 최선의 노력으로 가져온다."""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

URL_RE = re.compile(r"https?://[^\s<>\"'\)\]　]+")
TRAILING_PUNCT = ".,;:!?)]}>\"'"
# 로그인 벽이 있어 본문을 가져올 수 없는 도메인
SKIP_DOMAINS = ("instagram.com", "facebook.com", "fb.com", "threads.net", "fb.me")
USER_AGENT = "Mozilla/5.0 (compatible; igdm-digest/0.1; +https://github.com/)"
MAX_BYTES = 1_500_000


def unwrap_redirect(url: str) -> str:
    """l.instagram.com/?u=<encoded> 같은 래퍼 링크를 실제 URL 로 풀어준다."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return url
    host = (parsed.netloc or "").lower()
    if host in ("l.instagram.com", "l.facebook.com", "lm.facebook.com"):
        qs = urllib.parse.parse_qs(parsed.query)
        target = qs.get("u") or qs.get("url")
        if target:
            return target[0]
    return url


def extract_links(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for raw in URL_RE.findall(text):
        url = raw.rstrip(TRAILING_PUNCT)
        url = unwrap_redirect(url)
        if url and url not in out:
            out.append(url)
    return out


def is_skipped_domain(url: str) -> bool:
    host = (urllib.parse.urlparse(url).netloc or "").lower()
    return any(host == d or host.endswith("." + d) for d in SKIP_DOMAINS)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr", "section", "article"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return parser.title.strip(), text.strip()


def fetch_link_text(url: str, max_chars: int = 6000, timeout: int = 10) -> dict:
    """링크 본문을 텍스트로 가져온다. 실패해도 예외를 던지지 않고 결과 dict 에 기록한다."""
    result = {"url": url, "ok": False, "status": "error", "title": "", "text": "", "error": ""}
    if is_skipped_domain(url):
        result.update(status="skipped", error="로그인이 필요한 플랫폼 링크라 본문을 가져오지 않음")
        return result
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ko,en;q=0.8"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if not ("text/html" in ctype or "text/plain" in ctype or "xml" in ctype or ctype == ""):
                result.update(status="skipped", error=f"텍스트가 아닌 콘텐츠({ctype.split(';')[0]})")
                return result
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
        try:
            html = raw.decode(charset, errors="replace")
        except LookupError:
            html = raw.decode("utf-8", errors="replace")
        if "text/plain" in ctype:
            title, text = "", html
        else:
            title, text = html_to_text(html)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…(이하 생략)"
        result.update(ok=True, status="ok", title=title, text=text)
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - 네트워크 오류는 종류가 많아 모두 기록만 한다
        result["error"] = f"{type(e).__name__}: {e}"
    return result
