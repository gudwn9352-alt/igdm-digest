"""명령줄 인터페이스."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .actions import ActionStore, execute_action, parse_outreach_draft
from .analyze import ClaudeRunner
from .config import data_dir, load_config
from .deliver import DeliveryError, deliver_report, send_gmail
from .leads import find_leads
from .pipeline import load_last_run, run_pipeline
from .report import ACTION_LABEL, build_markdown, md_to_html


def _print(msg: str) -> None:
    print(msg, flush=True)


def cmd_run(args, cfg) -> int:
    if not args.export and not args.captured:
        _print("오류: --export <내보내기 zip/폴더> 또는 --captured <수집 JSON> 중 하나는 필요합니다.")
        return 2
    run = run_pipeline(cfg, export_path=args.export, captured_path=args.captured, deliver=not args.no_deliver, limit=args.limit, dry_run=args.dry_run)
    s = run["stats"]
    if args.dry_run:
        _print(
            f"[미리보기] 내 이름: {run.get('my_name') or '(미감지)'} · 대화방 {s['threads_total']}개 · 새 수신 메시지 {s['new_messages']}건 · "
            f"분석 예정 대화 {len(run.get('preview', []))}건 · 건너뜀 {s['skipped_old']}건 · 다음으로 미룸 {s['deferred']}개"
        )
        for p in run.get("preview", []):
            _print(f"  - {p['latest']} {p['sender']} ({p['new_messages']}건, 링크 {len(p['links'])}개) — {p['thread']}")
        for n in run.get("notes", []):
            _print(f"  ! {n}")
        return 0
    _print(f"완료: 분석 {s['analyzed']}건, 오류 {s['errors']}건, 제안 액션 {len(run['actions'])}개 · {run.get('delivery', '')}")
    if s.get("tokens"):
        t = s["tokens"]
        _print(f"토큰: 입력 {t['input_tokens']:,} / 출력 {t['output_tokens']:,} / 캐시읽기 {t['cache_read_input_tokens']:,} ({t['calls']}회 호출)")
    for n in run.get("notes", []):
        _print(f"  ! {n}")
    return 0


def cmd_actions(args, cfg) -> int:
    store = ActionStore(data_dir(cfg) / "actions.json")
    recs = store.list(args.status)
    if not recs:
        _print("액션이 없습니다.")
        return 0
    for r in recs:
        extra = f" → {r['result_path']}" if r.get("result_path") else ""
        to = f" to={r['to']}" if r.get("to") else ""
        _print(f"{r['id']}  [{r['status']:8}] [{ACTION_LABEL.get(r['type'], r['type'])}] {r['title']}  ({r.get('source', {}).get('sender', '')}){to}{extra}")
    return 0


def cmd_approve(args, cfg) -> int:
    store = ActionStore(data_dir(cfg) / "actions.json")
    for aid in args.ids:
        try:
            r = store.approve(aid, to=args.to)
            _print(f"승인: {r['id']} {r['title']}")
        except KeyError as e:
            _print(str(e))
    store.save()
    if args.run:
        return cmd_act(argparse.Namespace(ids=args.ids), cfg)
    _print("실행하려면: igdm act")
    return 0


def cmd_reject(args, cfg) -> int:
    store = ActionStore(data_dir(cfg) / "actions.json")
    for aid in args.ids:
        try:
            r = store.reject(aid)
            _print(f"거절: {r['id']} {r['title']}")
        except KeyError as e:
            _print(str(e))
    store.save()
    return 0


def cmd_act(args, cfg) -> int:
    store = ActionStore(data_dir(cfg) / "actions.json")
    targets = [r for r in store.list("approved") if not args.ids or any(r["id"].startswith(i) for i in args.ids)]
    if not targets:
        _print("실행할 승인된 액션이 없습니다. (igdm actions --status proposed 로 확인 후 igdm approve <id>)")
        return 0
    runner = ClaudeRunner(cfg)
    for r in targets:
        _print(f"실행 중: {r['id']} [{ACTION_LABEL.get(r['type'], r['type'])}] {r['title']}")
        execute_action(r, cfg, runner, data_dir(cfg))
        store.save()
        if r["status"] == "done":
            _print(f"  완료 → {r['result_path']}")
            if r["type"] == "outreach_email":
                _print(f"  초안을 확인한 뒤 보내려면: igdm send {r['id']} --to 받는주소 --yes")
        else:
            _print(f"  실패: {r.get('error')}")
    return 0


def cmd_send(args, cfg) -> int:
    store = ActionStore(data_dir(cfg) / "actions.json")
    r = store.get(args.id)
    if not r:
        _print(f"액션을 찾을 수 없습니다: {args.id}")
        return 1
    if r["type"] != "outreach_email" or not r.get("result_path") or not Path(r["result_path"]).exists():
        _print("보낼 수 있는 제안 메일 초안이 없습니다. 먼저 igdm approve <id> 후 igdm act 로 초안을 만드세요.")
        return 1
    subject, body = parse_outreach_draft(Path(r["result_path"]).read_text(encoding="utf-8"))
    subject = args.subject or subject or r["title"]
    _print(f"받는 사람: {args.to}\n제목: {subject}\n\n{body}\n")
    if "{" in body or "{" in subject:
        _print("경고: 초안에 {자리표시자} 가 남아 있습니다. 파일을 수정한 뒤 다시 실행하세요: " + r["result_path"])
        return 1
    if not args.yes:
        _print("위 내용으로 실제 발송하려면 --yes 를 붙여 다시 실행하세요. (그 전까지는 아무것도 보내지 않습니다)")
        return 0
    try:
        msg = send_gmail(cfg, to=args.to, subject=subject, text=body)
    except (DeliveryError, OSError) as e:
        _print(f"발송 실패: {e}")
        return 1
    r["to"] = args.to
    r["sent_at"] = datetime.now().isoformat(timespec="seconds")
    r["status"] = "sent"
    store.save()
    _print(msg)
    return 0


def cmd_leads(args, cfg) -> int:
    runner = ClaudeRunner(cfg)
    res = find_leads(runner, cfg, args.brief, region=args.region, count=args.count)
    out_dir = data_dir(cfg) / "leads"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"leads-{datetime.now():%Y%m%d-%H%M%S}.md"
    text = res["text"]
    if res.get("sources"):
        text += "\n\n## 검색한 출처\n" + "\n".join(f"- {u}" for u in res["sources"])
    path.write_text(text + "\n", encoding="utf-8")
    _print(text)
    _print(f"\n저장: {path}")
    return 0


def cmd_report(args, cfg) -> int:
    run = load_last_run(cfg)
    if not run:
        _print("저장된 실행 결과가 없습니다.")
        return 1
    md = build_markdown(run)
    if args.deliver:
        _print(deliver_report(cfg, subject=f"{cfg['delivery'].get('subject_prefix', '')} (재전송) {run.get('generated_at', '')}", markdown=md, html=md_to_html(md)))
    else:
        _print(md)
    return 0


def cmd_test_email(args, cfg) -> int:
    try:
        to = cfg["delivery"]["gmail"].get("to") or cfg["delivery"]["gmail"].get("from")
        _print(send_gmail(cfg, to=to, subject=f"{cfg['delivery'].get('subject_prefix', '')} 테스트 메일", text="igdm-digest 의 Gmail 발송 설정이 정상입니다."))
        return 0
    except (DeliveryError, OSError) as e:
        _print(f"실패: {e}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="igdm", description="인스타그램 DM 다이제스트: 유익한 정보만 골라 요약하고 사업 적용 액션을 제안·실행합니다.")
    p.add_argument("--config", default="config.yaml", help="설정 파일 경로 (기본: config.yaml)")
    p.add_argument("--version", action="version", version=f"igdm-digest {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="내보내기(또는 수집 JSON)를 읽어 분석·리포트·전달까지 한 번에 실행")
    r.add_argument("--export", help="인스타그램 내보내기 zip 또는 압축 해제 폴더")
    r.add_argument("--captured", help="브라우저 등으로 직접 수집한 메시지 JSON")
    r.add_argument("--limit", type=int, help="이번 실행에서 분석할 최대 대화방 수")
    r.add_argument("--no-deliver", action="store_true", help="리포트를 전달하지 않고 파일/상태만 저장")
    r.add_argument("--dry-run", action="store_true", help="Claude 호출 없이 무엇을 분석할지 미리보기 (상태 변경 없음)")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("actions", help="제안·승인·완료된 액션 목록")
    a.add_argument("--status", choices=["proposed", "approved", "done", "failed", "rejected", "sent"])
    a.set_defaults(func=cmd_actions)

    ap = sub.add_parser("approve", help="액션 승인 (실행은 igdm act, 또는 --run)")
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--to", help="제안 메일의 받는 주소(선택)")
    ap.add_argument("--run", action="store_true", help="승인 직후 바로 실행")
    ap.set_defaults(func=cmd_approve)

    rj = sub.add_parser("reject", help="액션 거절")
    rj.add_argument("ids", nargs="+")
    rj.set_defaults(func=cmd_reject)

    ac = sub.add_parser("act", help="승인된 액션 실행 (산출물 생성; 메일은 보내지 않음)")
    ac.add_argument("ids", nargs="*")
    ac.set_defaults(func=cmd_act)

    sd = sub.add_parser("send", help="제안 메일 초안을 실제 발송 (--yes 필요)")
    sd.add_argument("id")
    sd.add_argument("--to", required=True)
    sd.add_argument("--subject")
    sd.add_argument("--yes", action="store_true")
    sd.set_defaults(func=cmd_send)

    ld = sub.add_parser("leads", help="웹 검색으로 영업 대상 업체 찾기")
    ld.add_argument("brief", help="예: '홈페이지가 없거나 낡은 펜션'")
    ld.add_argument("--region")
    ld.add_argument("--count", type=int, default=10)
    ld.set_defaults(func=cmd_leads)

    rp = sub.add_parser("report", help="마지막 실행 리포트 다시 보기/재전송")
    rp.add_argument("--deliver", action="store_true")
    rp.set_defaults(func=cmd_report)

    te = sub.add_parser("test-email", help="Gmail 발송 설정 테스트")
    te.set_defaults(func=cmd_test_email)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        cfg = load_config(args.config, required=args.config != "config.yaml")
    except (FileNotFoundError, ValueError) as e:
        _print(str(e))
        return 2
    try:
        return args.func(args, cfg)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
