import json
import shutil
from pathlib import Path

from conftest import ME, build_sample_export, moj, ts
from igdm_digest.ingest import (
    assign_ownership, detect_my_name, fix_mojibake, load_captured, load_export, make_batches,
)
from igdm_digest.links import extract_links, unwrap_redirect


def test_fix_mojibake_roundtrip():
    original = "안녕하세요 👋 체크리스트 café"
    assert fix_mojibake(moj(original)) == original
    assert fix_mojibake("plain ascii http://x.y") == "plain ascii http://x.y"
    assert fix_mojibake("이미 정상인 한글") == "이미 정상인 한글"
    assert fix_mojibake(None) == ""


def test_extract_links_unwraps_instagram_redirect():
    text = "자료 👉 https://l.instagram.com/?u=https%3A%2F%2Fexample.com%2Fa%3Fx%3D1&e=AT0abc 그리고 https://foo.com/bar)."
    assert extract_links(text) == ["https://example.com/a?x=1", "https://foo.com/bar"]
    assert unwrap_redirect("https://example.com/x") == "https://example.com/x"


def test_load_export_parses_threads_and_detects_me(export_dir: Path):
    threads = load_export(export_dir, export_dir.parent / "extract")
    assert len(threads) == 4
    me = detect_my_name(threads)
    assert me == ME
    assign_ownership(threads, me)
    by_title = {t.title: t for t in threads}
    kim = by_title["김정보"]
    assert [m.sender for m in kim.messages] == ["김정보", ME, "김정보", "김정보"]  # 시간순 + 페이지 병합
    incoming = kim.incoming
    assert len(incoming) == 3
    assert "쇼피파이 해외 판매 체크리스트" in incoming[1].content
    assert incoming[1].links == ["https://example.com/shopify-checklist"]
    assert incoming[2].content == "해외 셀러가 꼭 보는 릴스"
    assert incoming[2].links == ["https://www.instagram.com/reel/ABC123/"]
    assert incoming[2].share["original_content_owner"] == "kim_info"
    assert "최요청" in by_title  # message_requests 포함


def test_load_export_excludes_message_requests_when_disabled(export_dir: Path):
    threads = load_export(export_dir, export_dir.parent / "extract", include_requests=False)
    assert {t.title for t in threads} == {"김정보", "박강의", "이반응"}


def test_load_export_from_zip(export_dir: Path, tmp_path: Path):
    zip_path = shutil.make_archive(str(tmp_path / "instagram-export"), "zip", root_dir=export_dir)
    threads = load_export(zip_path, tmp_path / "extract")
    assert {t.title for t in threads} == {"김정보", "박강의", "이반응", "최요청"}


def test_make_batches_filters_seen_reactions_and_old(export_dir: Path):
    threads = load_export(export_dir, export_dir.parent / "extract")
    assign_ownership(threads, detect_my_name(threads))
    batches, auto_skip = make_batches(threads, set(), since_ms=ts("2026-08-01T00:00:00+09:00"))
    titles = [b.thread.title for b in batches]
    assert titles == ["최요청", "박강의", "김정보"]  # 최신 메시지 순
    assert len(auto_skip) == 2  # 오래된 메시지 1 + 반응 메시지 1
    kim = next(b for b in batches if b.thread.title == "김정보")
    assert len(kim.new_messages) == 2 and kim.sender == "김정보"
    assert [m.content for m in kim.context_messages] == ["오래된 메시지입니다", "정보"]
    assert kim.all_links == ["https://example.com/shopify-checklist", "https://www.instagram.com/reel/ABC123/"]

    seen = {m.id for m in kim.new_messages}
    batches2, _ = make_batches(threads, seen, since_ms=ts("2026-08-01T00:00:00+09:00"))
    assert [b.thread.title for b in batches2] == ["최요청", "박강의"]
    batches3, _ = make_batches(threads, set(), limit=1)
    assert len(batches3) == 1


def test_detect_my_name_prefers_config_and_needs_two_threads(tmp_path: Path):
    root = build_sample_export(tmp_path / "e")
    threads = load_export(root, tmp_path / "x")
    assert detect_my_name(threads, "설정이름") == "설정이름"
    assert detect_my_name(threads[:1]) is None


def test_load_captured_json(tmp_path: Path):
    path = tmp_path / "captured.json"
    path.write_text(json.dumps([
        {"thread": "정보맨", "sender": "정보맨", "timestamp": "2026-10-06T10:00:00+09:00", "text": "자료 링크 https://example.com/doc"},
        {"thread": "정보맨", "sender": "나", "timestamp": "2026-10-06T10:01:00+09:00", "text": "감사합니다", "from_me": True},
        {"thread": "다른사람", "sender": "다른사람", "timestamp": 1759795200000, "text": "안녕하세요", "links": ["https://x.com/a"]},
    ], ensure_ascii=False), encoding="utf-8")
    threads = load_captured(path)
    assert len(threads) == 2
    t = next(t for t in threads if t.title == "정보맨")
    assert t.source == "captured" and len(t.incoming) == 1 and t.incoming[0].links == ["https://example.com/doc"]
    other = next(t for t in threads if t.title == "다른사람")
    assert other.messages[0].links == ["https://x.com/a"] and other.messages[0].timestamp_ms == 1759795200000
