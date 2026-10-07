"""전체 흐름: 읽기 → 새 메시지 선별 → 링크 본문 수집 → 분석 → 액션 저장(+자동 실행) → 리포트 → 전달 → 상태 저장."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import anthropic

from .actions import SAFE_AUTO_TYPES, ActionStore, execute_action
from .analyze import Analyzer, ClaudeError, ClaudeRunner
from .config import data_dir as _data_dir
from .deliver import DeliveryError, deliver_report
from .ingest import assign_ownership, detect_my_name, get_timezone, load_captured, load_export, make_batches
from .links import fetch_link_text
from .report import build_markdown, md_to_html
from .state import State

MAX_LINKS_PER_THREAD = 5


def load_threads(cfg: dict, *, export_path=None, captured_path=None):
    """내보내기와 수집 JSON 을 읽어 (대화방 목록, 감지된 내 이름, 참고 메모) 를 돌려준다."""
    notes: list[str] = []
    threads = []
    data = _data_dir(cfg)
    if export_path:
        threads += load_export(export_path, data / "exports", include_requests=bool(cfg["instagram"].get("include_message_requests", True)))
    if captured_path:
        threads += load_captured(captured_path)
    if not threads:
        notes.append("읽을 대화방이 없습니다. 내보내기 경로(--export) 또는 수집 파일(--captured)을 확인하세요.")
    my_name = detect_my_name(threads, cfg["instagram"].get("my_name") or "")
    if export_path and not my_name:
        notes.append("내 이름을 자동 감지하지 못했습니다. config.yaml 의 instagram.my_name 을 설정하세요. (지금은 모든 메시지를 수신 메시지로 취급)")
    assign_ownership(threads, my_name)
    return threads, my_name, notes


def _sum_tokens(calls: list[dict]) -> dict:
    total = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "calls": 0}
    for c in calls:
        if "degraded" in c:
            continue
        total["calls"] += 1
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            total[k] += int(c.get(k) or 0)
    return total


def run_pipeline(
    cfg: dict,
    *,
    export_path=None,
    captured_path=None,
    runner: ClaudeRunner | None = None,
    deliver: bool = True,
    limit: int | None = None,
    dry_run: bool = False,
    smtp_factory=None,
    now: datetime | None = None,
) -> dict:
    data = _data_dir(cfg)
    tz = get_timezone(cfg["instagram"].get("timezone", "Asia/Seoul"))
    now = now or datetime.now(tz)
    state = State(data / "state.json")
    store = ActionStore(data / "actions.json")
    a_cfg = cfg["analysis"]

    threads, my_name, notes = load_threads(cfg, export_path=export_path, captured_path=captured_path)

    since_days = int(a_cfg.get("since_days") or 0)
    since_ms = int((now - timedelta(days=since_days)).timestamp() * 1000) if since_days > 0 else None
    batches, auto_skip = make_batches(threads, state.seen, context_n=int(a_cfg.get("context_messages", 10)), since_ms=since_ms)
    cap = limit if limit is not None else int(a_cfg.get("max_threads_per_run") or 0)
    deferred = max(0, len(batches) - cap) if cap > 0 else 0
    if cap > 0:
        batches = batches[:cap]

    run: dict = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "my_name": my_name,
        "min_usefulness_to_report": int(a_cfg.get("min_usefulness_to_report", 40)),
        "stats": {
            "threads_total": len(threads),
            "new_messages": sum(len(b.new_messages) for b in batches),
            "analyzed": 0,
            "skipped_old": len(auto_skip),
            "deferred": deferred,
            "errors": 0,
        },
        "items": [],
        "actions": [],
        "errors": [],
        "notes": notes,
        "dry_run": dry_run,
    }
    if dry_run:
        run["preview"] = [
            {
                "thread": b.thread.title,
                "sender": b.sender,
                "new_messages": len(b.new_messages),
                "links": b.all_links,
                "latest": b.new_messages[-1].dt(tz).strftime("%Y-%m-%d %H:%M"),
            }
            for b in batches
        ]
        return run

    runner = runner or ClaudeRunner(cfg)
    analyzer = Analyzer(cfg, runner)
    fetch_links = bool(a_cfg.get("fetch_links", True))
    max_link_chars = int(a_cfg.get("max_link_chars", 6000))

    for batch in batches:
        link_docs = []
        if fetch_links:
            link_docs = [fetch_link_text(u, max_chars=max_link_chars) for u in batch.all_links[:MAX_LINKS_PER_THREAD]]
        try:
            analysis = analyzer.analyze_batch(batch, link_docs, tz)
        except (ClaudeError, anthropic.APIError, ValueError) as e:
            run["errors"].append({"thread_title": batch.thread.title, "sender": batch.sender, "error": f"{type(e).__name__}: {e}"})
            run["stats"]["errors"] += 1
            continue
        top_fit = analysis["business_fit"][0] if analysis["business_fit"] else {}
        source = {"thread_path": batch.thread.thread_path, "thread_title": batch.thread.title, "sender": batch.sender, "topic": analysis["topic"]}
        context = {"topic": analysis["topic"], "summary": analysis["summary"], "key_points": analysis["key_points"], "how_to_apply": top_fit.get("how_to_apply", "")}
        records = store.add_proposals(analysis["proposed_actions"], source=source, context=context) if analysis["category"] in ("useful", "mixed") else []
        received = ", ".join(sorted({m.dt(tz).strftime("%Y-%m-%d") for m in batch.new_messages}))
        run["items"].append({
            "thread_title": batch.thread.title,
            "thread_path": batch.thread.thread_path,
            "sender": batch.sender,
            "source": batch.thread.source,
            "received": received,
            "messages": [{"sender": m.sender, "at": m.dt(tz).strftime("%Y-%m-%d %H:%M"), "content": m.content} for m in batch.new_messages],
            "links": [{k: d.get(k) for k in ("url", "status", "title", "error")} for d in link_docs],
            "analysis": {k: v for k, v in analysis.items() if k != "_meta"},
            "actions": records,
        })
        run["actions"].extend(records)
        run["stats"]["analyzed"] += 1
        state.mark_seen(m.id for m in batch.new_messages)

    state.mark_seen(auto_skip)

    auto_types = {t for t in (cfg.get("actions", {}).get("auto_execute") or []) if t in SAFE_AUTO_TYPES}
    for rec in run["actions"]:
        if rec["type"] in auto_types:
            execute_action(rec, cfg, runner, data)

    run["stats"]["tokens"] = _sum_tokens(getattr(runner, "calls", []))
    runs_dir = data / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_path = runs_dir / f"run-{now.strftime('%Y%m%d-%H%M%S')}.json"
    run["run_path"] = str(run_path)

    markdown = build_markdown(run)
    html = md_to_html(markdown)
    attachments = [Path(r["result_path"]) for r in run["actions"] if r.get("status") == "done" and r.get("result_path")]
    if deliver:
        useful = sum(1 for i in run["items"] if i["analysis"]["category"] in ("useful", "mixed"))
        subject = f"{cfg['delivery'].get('subject_prefix', '[IG DM 다이제스트]')} {run['generated_at']} · 유익 {useful}건"
        try:
            run["delivery"] = deliver_report(cfg, subject=subject, markdown=markdown, html=html, attachments=attachments, smtp_factory=smtp_factory)
        except (DeliveryError, OSError) as e:
            fallback_dir = data / "reports"
            fallback_dir.mkdir(parents=True, exist_ok=True)
            fallback = fallback_dir / f"digest-{now.strftime('%Y%m%d-%H%M%S')}.md"
            fallback.write_text(markdown, encoding="utf-8")
            run["delivery"] = f"전달 실패({type(e).__name__}: {e}) → 파일로 저장: {fallback}"
            run["notes"].append(run["delivery"])
    else:
        run["delivery"] = "전달 생략(--no-deliver)"
    run["markdown"] = markdown

    store.save()
    state.record_run({"at": run["generated_at"], **{k: v for k, v in run["stats"].items() if k != "tokens"}, "delivery": run["delivery"]})
    state.save()
    run_path.write_text(json.dumps({k: v for k, v in run.items() if k != "markdown"}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return run


def load_last_run(cfg: dict) -> dict | None:
    runs_dir = _data_dir(cfg) / "runs"
    files = sorted(runs_dir.glob("run-*.json")) if runs_dir.exists() else []
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))
