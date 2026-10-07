"""테스트 공통 도구: 인스타그램식 내보내기 파일 생성기, 가짜 Claude 러너, 설정."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from igdm_digest.config import load_config, deep_merge

ME = "나"


def moj(s: str) -> str:
    """인스타그램 내보내기처럼 UTF-8 바이트를 latin-1 문자로 깨뜨린다."""
    return s.encode("utf-8").decode("latin-1")


def ts(iso: str) -> int:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def write_thread(root: Path, folder: str, dirname: str, participants: list[str], messages: list[dict], title: str | None = None, split: int | None = None) -> Path:
    d = root / "your_instagram_activity" / "messages" / folder / dirname
    d.mkdir(parents=True, exist_ok=True)
    raw_msgs = []
    for m in messages:
        raw = {"sender_name": moj(m["sender"]), "timestamp_ms": m["ts"]}
        if m.get("content") is not None:
            raw["content"] = moj(m["content"])
        if m.get("share"):
            raw["share"] = {k: moj(v) for k, v in m["share"].items()}
        if m.get("photos"):
            raw["photos"] = [{"uri": "x.jpg"}]
        raw_msgs.append(raw)
    # 인스타그램은 최신 메시지가 앞에 오도록 저장한다
    raw_msgs.sort(key=lambda r: r["timestamp_ms"], reverse=True)
    chunks = [raw_msgs] if not split else [raw_msgs[i : i + split] for i in range(0, len(raw_msgs), split)]
    for i, chunk in enumerate(chunks, start=1):
        payload = {
            "participants": [{"name": moj(p)} for p in participants],
            "messages": chunk,
            "title": moj(title) if title is not None else moj(participants[0]),
            "is_still_participant": True,
            "thread_path": f"{folder}/{dirname}",
            "magic_words": [],
        }
        (d / f"message_{i}.json").write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    return d


def build_sample_export(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    write_thread(root, "inbox", "kiminfo_111", ["김정보", ME], [
        {"sender": "김정보", "ts": ts("2024-01-01T10:00:00+09:00"), "content": "오래된 메시지입니다"},
        {"sender": ME, "ts": ts("2026-09-30T09:00:00+09:00"), "content": "정보"},
        {"sender": "김정보", "ts": ts("2026-09-30T09:01:00+09:00"),
         "content": "안녕하세요! 요청하신 '쇼피파이 해외 판매 체크리스트' 보내드려요 👉 https://l.instagram.com/?u=https%3A%2F%2Fexample.com%2Fshopify-checklist&e=AT0abc"},
        {"sender": "김정보", "ts": ts("2026-09-30T09:02:00+09:00"), "content": None,
         "share": {"link": "https://www.instagram.com/reel/ABC123/", "share_text": "해외 셀러가 꼭 보는 릴스", "original_content_owner": "kim_info"}},
    ], split=2)
    write_thread(root, "inbox", "parkclass_222", ["박강의", ME], [
        {"sender": "박강의", "ts": ts("2026-10-02T20:00:00+09:00"),
         "content": "선착순 30명 무료 특강! 지금 신청하세요 https://example.com/free-class (수익 인증 월 1억)"},
    ])
    write_thread(root, "inbox", "leereact_333", ["이반응", ME], [
        {"sender": "이반응", "ts": ts("2026-10-03T12:00:00+09:00"), "content": "이반응님이 메시지에 ❤️ 반응을 남겼습니다"},
        {"sender": ME, "ts": ts("2026-10-03T12:01:00+09:00"), "content": "ㅎㅎ"},
    ])
    write_thread(root, "message_requests", "choireq_444", ["최요청", ME], [
        {"sender": "최요청", "ts": ts("2026-10-05T08:00:00+09:00"), "content": "협찬 제안드립니다. 자세한 내용은 답장 주세요."},
    ])
    return root


ANALYSES = {
    "김정보": {
        "category": "useful", "usefulness_score": 82, "funnel_score": 15,
        "topic": "쇼피파이 해외 판매 체크리스트", "verdict": "바로 쓸 수 있는 체크리스트",
        "summary": "해외 타깃 쇼피파이 스토어를 열 때 확인할 항목을 정리한 자료입니다.",
        "key_points": ["결제·배송 설정", "타깃 국가 선정", "광고 초기 예산"],
        "red_flags": [], "evidence": ["체크리스트 보내드려요"],
        "business_fit": [
            {"business": "쇼핑몰 (국내 + 해외 타깃 Shopify)", "fit_score": 85, "how_to_apply": "체크리스트대로 스토어 세팅", "expected_value": "세팅 시간 단축 (추정)", "effort": "medium"},
            {"business": "릴스 영상 제작·수익화", "fit_score": 20, "how_to_apply": "해당 없음", "expected_value": "", "effort": "low"},
        ],
        "proposed_actions": [
            {"type": "checklist", "title": "해외 Shopify 스토어 오픈 체크리스트 실행", "detail": "7일 안에 첫 주문을 목표로", "business": "쇼핑몰 (국내 + 해외 타깃 Shopify)", "priority": "this_month"},
            {"type": "outreach_email", "title": "펜션 홈페이지 제작 제안 메일", "detail": "강원 지역 펜션 대상, 7일 납기 패키지", "business": "소상공인 홈페이지 제작 대행", "priority": "this_week"},
        ],
    },
    "박강의": {
        "category": "funnel", "usefulness_score": 10, "funnel_score": 95,
        "topic": "무료 특강 유도", "verdict": "정보 없이 특강 신청 유도",
        "summary": "선착순 압박과 수익 인증으로 특강 신청을 유도합니다.",
        "key_points": [], "red_flags": ["선착순/마감 압박", "수익 인증 과장"], "evidence": ["선착순 30명 무료 특강"],
        "business_fit": [], "proposed_actions": [
            {"type": "checklist", "title": "무시해도 될 액션", "detail": "", "business": "", "priority": "later"},
        ],
    },
}
DEFAULT_ANALYSIS = {
    "category": "noise", "usefulness_score": 5, "funnel_score": 5, "topic": "기타", "verdict": "내용 없음",
    "summary": "", "key_points": [], "red_flags": [], "evidence": [], "business_fit": [], "proposed_actions": [],
}


class FakeRunner:
    """Claude 를 호출하지 않고 보낸 사람 이름에 따라 미리 정한 분석 결과를 돌려준다."""

    def __init__(self):
        self.calls: list[dict] = []
        self.prompts: list[str] = []

    def _meta(self):
        return {"model": "fake", "input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 0, "fallback_ran": False}

    def structured(self, system, user, schema, **kw):
        self.prompts.append(user)
        self.calls.append({"label": kw.get("label", "structured"), **self._meta()})
        for sender, analysis in ANALYSES.items():
            if f'sender="{sender}"' in user:
                return {"data": json.loads(json.dumps(analysis)), "meta": self._meta()}
        return {"data": dict(DEFAULT_ANALYSIS), "meta": self._meta()}

    def text(self, system, user, **kw):
        self.prompts.append(user)
        self.calls.append({"label": kw.get("label", "text"), **self._meta()})
        if "제안 메일" in user or "메일 목적" in user:
            return {"text": "제목: 펜션 홈페이지, 7일 안에 새로 만들어 드립니다\n\n{업체명} 대표님 안녕하세요.\n홈페이지가 없어 예약 손님을 놓치고 계신 것 같아 연락드립니다.", "meta": self._meta()}
        return {"text": "## 산출물\n\n- 1단계: 스토어 개설\n- 2단계: 결제 연결", "meta": self._meta()}

    def web_research(self, system, user, **kw):
        self.prompts.append(user)
        self.calls.append({"label": kw.get("label", "web_research"), **self._meta()})
        return {"text": "| 업체명 | 지역 |\n|---|---|\n| 바다뷰펜션 | 강릉 |", "sources": ["https://example.com/pension"], "meta": self._meta()}


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    return build_sample_export(tmp_path / "export")


@pytest.fixture
def cfg(tmp_path: Path) -> dict:
    base = load_config(None)
    return deep_merge(base, {
        "instagram": {"my_name": ""},
        "analysis": {"fetch_links": False, "since_days": 60, "min_usefulness_to_report": 40},
        "business": {"owner": "테스트", "summary": "온라인 수익", "goals": {"this_week": "7일 안에 100만원", "ongoing": "지속 성장"},
                      "lines": [{"name": "쇼핑몰 (국내 + 해외 타깃 Shopify)", "status": "매출 0", "notes": ""}]},
        "delivery": {"method": "file", "file": {"dir": str(tmp_path / "reports")}},
        "paths": {"data_dir": str(tmp_path / "data")},
    })


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def fixed_now():
    from zoneinfo import ZoneInfo
    return datetime(2026, 10, 7, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
