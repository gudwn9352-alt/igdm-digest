"""인스타그램 '내 정보 다운로드' 내보내기(JSON) 와 브라우저로 수집한 메시지 JSON 을 공통 구조로 읽어들인다."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .links import extract_links

MESSAGE_FILE_RE = re.compile(r"^message_\d+\.json$")
REACTION_RE = re.compile(
    r"(reacted .{0,40} to your message|liked a message|반응을 남겼습니다|메시지를 좋아합니다)",
    re.IGNORECASE,
)


@dataclass
class Message:
    id: str
    thread_path: str
    thread_title: str
    sender: str
    timestamp_ms: int
    content: str
    links: list[str] = field(default_factory=list)
    share: Optional[dict] = None
    is_from_me: bool = False
    source: str = "export"

    def dt(self, tz: ZoneInfo | timezone = timezone.utc) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc).astimezone(tz)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Thread:
    thread_path: str
    title: str
    participants: list[str]
    messages: list[Message]
    source: str = "export"

    @property
    def incoming(self) -> list[Message]:
        return [m for m in self.messages if not m.is_from_me]


@dataclass
class ThreadBatch:
    """한 대화방에서 아직 분석하지 않은 새 수신 메시지 묶음 + 맥락."""

    thread: Thread
    new_messages: list[Message]
    context_messages: list[Message]

    @property
    def sender(self) -> str:
        counts = Counter(m.sender for m in self.new_messages)
        return counts.most_common(1)[0][0] if counts else ""

    @property
    def latest_ms(self) -> int:
        return max((m.timestamp_ms for m in self.new_messages), default=0)

    @property
    def all_links(self) -> list[str]:
        out: list[str] = []
        for m in self.new_messages:
            for link in m.links:
                if link not in out:
                    out.append(link)
        return out


def fix_mojibake(s: str | None) -> str:
    """인스타그램 내보내기는 UTF-8 바이트를 latin-1 문자로 하나씩 이스케이프한다. 되돌릴 수 있으면 되돌린다."""
    if not s:
        return ""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def get_timezone(name: str) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001
        return timezone.utc


def _message_id(thread_path: str, timestamp_ms: int, sender: str, content: str) -> str:
    h = hashlib.sha1(f"{thread_path}|{timestamp_ms}|{sender}|{content}".encode("utf-8")).hexdigest()
    return h[:16]


def _placeholder_content(raw: dict) -> str:
    if raw.get("photos"):
        return "[사진]"
    if raw.get("videos"):
        return "[동영상]"
    if raw.get("audio_files"):
        return "[음성 메시지]"
    if raw.get("sticker"):
        return "[스티커]"
    return ""


def _parse_raw_message(raw: dict, thread_path: str, title: str) -> Message | None:
    if not isinstance(raw, dict):
        return None
    sender = fix_mojibake(raw.get("sender_name"))
    try:
        ts = int(raw.get("timestamp_ms") or 0)
    except (TypeError, ValueError):
        ts = 0
    content = fix_mojibake(raw.get("content"))
    share = raw.get("share") if isinstance(raw.get("share"), dict) else None
    if share:
        share = {k: (fix_mojibake(v) if isinstance(v, str) else v) for k, v in share.items()}
    if not content:
        content = (share or {}).get("share_text") or _placeholder_content(raw)
    links = extract_links(content)
    if share and share.get("link") and share["link"] not in links:
        links.append(share["link"])
    if not content and not links:
        return None
    return Message(
        id=_message_id(thread_path, ts, sender, content),
        thread_path=thread_path,
        thread_title=title,
        sender=sender,
        timestamp_ms=ts,
        content=content,
        links=links,
        share=share,
    )


def _parse_thread_files(files: list[Path], root: Path) -> Thread | None:
    participants: list[str] = []
    title = ""
    thread_path = ""
    messages: list[Message] = []
    for fp in sorted(files):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or "messages" not in data:
            continue
        if not participants:
            participants = [fix_mojibake(p.get("name")) for p in data.get("participants", []) if isinstance(p, dict)]
        if not title:
            title = fix_mojibake(data.get("title"))
        if not thread_path:
            thread_path = data.get("thread_path") or str(fp.parent.relative_to(root)).replace("\\", "/")
        for raw in data.get("messages", []):
            m = _parse_raw_message(raw, thread_path, title)
            if m:
                messages.append(m)
    if not messages and not participants:
        return None
    messages.sort(key=lambda m: m.timestamp_ms)
    return Thread(thread_path=thread_path, title=title, participants=participants, messages=messages)


def _extract_zip(path: Path, extract_dir: Path) -> Path:
    target = extract_dir / path.stem
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            # zip slip 방지: 추출 경로가 대상 폴더 밖으로 나가면 건너뛴다
            dest = (target / info.filename).resolve()
            if not str(dest).startswith(str(target.resolve())):
                continue
            zf.extract(info, target)
    return target


def load_export(path: str | Path, extract_dir: str | Path, include_requests: bool = True) -> list[Thread]:
    """내보내기 zip 또는 압축 해제된 폴더에서 모든 대화방을 읽는다."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"내보내기 경로가 없습니다: {p}")
    root = _extract_zip(p, Path(extract_dir)) if p.is_file() and p.suffix.lower() == ".zip" else p
    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for fp in root.rglob("message_*.json"):
        if not MESSAGE_FILE_RE.match(fp.name):
            continue
        parts = {x.lower() for x in fp.relative_to(root).parts}
        if "message_requests" in parts and not include_requests:
            continue
        by_dir[fp.parent].append(fp)
    threads: list[Thread] = []
    for d, files in sorted(by_dir.items()):
        t = _parse_thread_files(files, root)
        if t:
            threads.append(t)
    return threads


def _parse_timestamp(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value if value > 1e12 else value * 1000)
    s = str(value).strip()
    if s.isdigit():
        return _parse_timestamp(int(s))
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_captured(path: str | Path) -> list[Thread]:
    """브라우저(크롬) 등으로 직접 수집한 간단한 메시지 JSON 을 읽는다.

    형식: [{"thread": "보낸사람 이름", "sender": "...", "timestamp": "2026-10-01T09:00:00+09:00" 또는 ms,
            "text": "...", "links": [...], "from_me": false}, ...]
    """
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "messages" in data:
        data = data["messages"]
    if not isinstance(data, list):
        raise ValueError("captured JSON 은 메시지 객체의 배열이어야 합니다")
    grouped: dict[str, list[Message]] = defaultdict(list)
    for raw in data:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("thread") or raw.get("sender") or "unknown").strip()
        thread_path = "captured/" + re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", title)[:60]
        content = str(raw.get("text") or raw.get("content") or "").strip()
        links = extract_links(content)
        for link in raw.get("links") or []:
            if link not in links:
                links.append(link)
        if not content and not links:
            continue
        sender = str(raw.get("sender") or title)
        ts = _parse_timestamp(raw.get("timestamp") or raw.get("timestamp_ms"))
        grouped[thread_path].append(
            Message(
                id=_message_id(thread_path, ts, sender, content),
                thread_path=thread_path,
                thread_title=title,
                sender=sender,
                timestamp_ms=ts,
                content=content,
                links=links,
                is_from_me=bool(raw.get("from_me", False)),
                source="captured",
            )
        )
    threads = []
    for thread_path, msgs in grouped.items():
        msgs.sort(key=lambda m: m.timestamp_ms)
        participants = sorted({m.sender for m in msgs})
        threads.append(Thread(thread_path=thread_path, title=msgs[0].thread_title, participants=participants, messages=msgs, source="captured"))
    return threads


def detect_my_name(threads: list[Thread], configured: str = "") -> str | None:
    """설정에 이름이 있으면 그걸 쓰고, 없으면 대부분의 대화방에 공통으로 등장하는 참가자를 나로 본다."""
    if configured:
        return configured
    export_threads = [t for t in threads if t.source == "export"]
    if len(export_threads) < 2:
        return None
    counts: Counter[str] = Counter()
    for t in export_threads:
        for name in set(t.participants):
            if name:
                counts[name] += 1
    if not counts:
        return None
    name, n = counts.most_common(1)[0]
    if n >= max(2, int(len(export_threads) * 0.6)):
        return name
    return None


def assign_ownership(threads: list[Thread], my_name: str | None) -> None:
    for t in threads:
        if t.source == "export":
            for m in t.messages:
                m.is_from_me = bool(my_name) and m.sender == my_name
        if not t.title:
            others = [p for p in t.participants if p != my_name]
            t.title = ", ".join(others) or (t.participants[0] if t.participants else t.thread_path)
        for m in t.messages:
            m.thread_title = t.title


def make_batches(
    threads: list[Thread],
    seen: set[str],
    *,
    context_n: int = 10,
    since_ms: int | None = None,
    limit: int | None = None,
) -> tuple[list[ThreadBatch], list[str]]:
    """새 수신 메시지가 있는 대화방을 배치로 묶는다. 반환: (배치, 분석 없이 처리완료로 표시할 id 목록)."""
    batches: list[ThreadBatch] = []
    auto_skip: list[str] = []
    for t in threads:
        fresh = [m for m in t.incoming if m.id not in seen]
        new: list[Message] = []
        for m in fresh:
            if REACTION_RE.search(m.content):
                auto_skip.append(m.id)
            elif since_ms is not None and m.timestamp_ms < since_ms:
                auto_skip.append(m.id)
            else:
                new.append(m)
        if not new:
            continue
        new_ids = {m.id for m in new}
        context = [m for m in t.messages if m.id not in new_ids][-context_n:] if context_n > 0 else []
        batches.append(ThreadBatch(thread=t, new_messages=new, context_messages=context))
    batches.sort(key=lambda b: b.latest_ms, reverse=True)
    if limit is not None and limit >= 0:
        batches = batches[:limit]
    return batches, auto_skip
