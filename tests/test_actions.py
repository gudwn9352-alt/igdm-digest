from pathlib import Path

from conftest import FakeRunner
from igdm_digest.actions import ActionStore, execute_action, make_action_id, parse_outreach_draft


def _proposals():
    return [
        {"type": "checklist", "title": "체크리스트 실행", "detail": "7일", "business": "쇼핑몰", "priority": "this_month"},
        {"type": "outreach_email", "title": "펜션 제안 메일", "detail": "강원", "business": "홈페이지 제작", "priority": "this_week"},
        {"type": "bogus", "title": "무시"},
    ]


def test_store_add_dedupe_approve_reject(tmp_path: Path):
    store = ActionStore(tmp_path / "actions.json")
    added = store.add_proposals(_proposals(), source={"thread_path": "inbox/a", "sender": "김"}, context={"summary": "s"})
    assert [a["type"] for a in added] == ["checklist", "outreach_email"]
    assert added[1]["priority"] == "this_week"
    assert store.add_proposals(_proposals(), source={"thread_path": "inbox/a"}, context={}) == []  # 중복 방지
    assert added[0]["id"] == make_action_id("inbox/a", "checklist", "체크리스트 실행")
    store.approve(added[0]["id"][:4], to=None)
    store.reject(added[1]["id"])
    store.save()
    reloaded = ActionStore(tmp_path / "actions.json")
    assert reloaded.list("approved")[0]["title"] == "체크리스트 실행"
    assert reloaded.list("rejected")[0]["title"] == "펜션 제안 메일"


def test_execute_checklist_and_outreach_draft(tmp_path: Path, cfg):
    store = ActionStore(tmp_path / "actions.json")
    added = store.add_proposals(_proposals(), source={"thread_path": "inbox/a", "sender": "김정보", "thread_title": "김정보"}, context={"topic": "t", "summary": "요약", "key_points": ["k"], "how_to_apply": "h"})
    runner = FakeRunner()
    rec = execute_action(added[0], cfg, runner, tmp_path / "data")
    assert rec["status"] == "done"
    out = Path(rec["result_path"])
    assert out.exists() and out.name.startswith(out.name[:8]) and "-checklist-" in out.name
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# 체크리스트 실행") and "1단계: 스토어 개설" in text
    assert "요약" in runner.prompts[-1] and "<dm" in runner.prompts[-1]

    rec2 = execute_action(added[1], cfg, runner, tmp_path / "data")
    assert rec2["status"] == "done"
    draft = Path(rec2["result_path"]).read_text(encoding="utf-8")
    assert "아직 발송되지 않았습니다" in draft and f"igdm send {rec2['id']}" in draft
    subject, body = parse_outreach_draft(draft)
    assert subject == "펜션 홈페이지, 7일 안에 새로 만들어 드립니다"
    assert body.startswith("{업체명} 대표님") and "igdm send" not in body


def test_execute_records_failure_without_raising(tmp_path: Path, cfg):
    class Boom(FakeRunner):
        def text(self, *a, **k):
            raise RuntimeError("api down")

    store = ActionStore(tmp_path / "actions.json")
    rec = store.add_proposals(_proposals()[:1], source={"thread_path": "x"}, context={})[0]
    execute_action(rec, cfg, Boom(), tmp_path / "data")
    assert rec["status"] == "failed" and "api down" in rec["error"]


def test_execute_lead_search_and_research_use_web(tmp_path: Path, cfg):
    store = ActionStore(tmp_path / "actions.json")
    recs = store.add_proposals([
        {"type": "lead_search", "title": "강원 펜션 찾기", "detail": "홈페이지 없는 곳", "business": "홈페이지", "priority": "this_week"},
        {"type": "research", "title": "쇼피파이 수수료 조사", "detail": "", "business": "쇼핑몰", "priority": "later"},
    ], source={"thread_path": "x", "sender": "김"}, context={})
    runner = FakeRunner()
    for r in recs:
        execute_action(r, cfg, runner, tmp_path / "data")
        assert r["status"] == "done"
        assert "검색한 출처" in Path(r["result_path"]).read_text(encoding="utf-8")
    assert [c["label"] for c in runner.calls] == ["leads", f"research:{recs[1]['id']}"]
