"""실행 결과(run) 를 한국어 마크다운/HTML 리포트로 만든다."""
from __future__ import annotations

import html
import re

CATEGORY_LABEL = {"useful": "유익", "mixed": "혼합(주의)", "funnel": "유입·판매용", "noise": "노이즈"}
ACTION_LABEL = {
    "checklist": "실행 체크리스트",
    "content_brief": "콘텐츠/영상 기획안",
    "experiment": "실험 설계",
    "research": "추가 조사",
    "lead_search": "영업 대상 업체 찾기",
    "outreach_email": "제안 메일 초안",
}
EFFORT_LABEL = {"low": "낮음", "medium": "보통", "high": "높음"}
PRIORITY_LABEL = {"this_week": "이번 주 현금화", "this_month": "이달 안", "later": "기반 작업"}
PRIORITY_ORDER = {"this_week": 0, "this_month": 1, "later": 2}


def _item_header(item: dict) -> str:
    a = item["analysis"]
    return f"{a.get('topic') or item['thread_title']} — {item['sender']} ({item['received']})"


def _render_item(item: dict, full: bool) -> list[str]:
    a = item["analysis"]
    lines = [f"### {_item_header(item)}"]
    lines.append(
        f"- 분류: **{CATEGORY_LABEL.get(a['category'], a['category'])}** · 유익도 {a['usefulness_score']}/100 · 판매·유입 의도 {a['funnel_score']}/100"
    )
    if a.get("verdict"):
        lines.append(f"- 한 줄 판단: {a['verdict']}")
    if not full:
        if a.get("red_flags"):
            lines.append(f"- 주의 신호: {', '.join(a['red_flags'][:3])}")
        lines.append("")
        return lines
    if a.get("summary"):
        lines.append("")
        lines.append(a["summary"])
    if a.get("key_points"):
        lines.append("")
        lines.append("**핵심 포인트**")
        lines.extend(f"- {p}" for p in a["key_points"])
    if a.get("red_flags"):
        lines.append("")
        lines.append("**주의 신호**")
        lines.extend(f"- {p}" for p in a["red_flags"])
    fits = [f for f in a.get("business_fit", []) if f["fit_score"] >= 40]
    if fits:
        lines.append("")
        lines.append("**내 사업에 적용하면**")
        for f in fits:
            lines.append(f"- {f['business']} (적합도 {f['fit_score']}, 난이도 {EFFORT_LABEL.get(f['effort'], f['effort'])}): {f['how_to_apply']}")
            if f.get("expected_value"):
                lines.append(f"  - 기대 효과: {f['expected_value']}")
    if item.get("links"):
        lines.append("")
        lines.append("**링크**")
        for doc in item["links"]:
            status = {"ok": "본문 확인", "skipped": "본문 생략", "error": "가져오기 실패"}.get(doc.get("status"), doc.get("status", ""))
            lines.append(f"- {doc.get('url')} ({status})")
    acts = item.get("actions", [])
    if acts:
        lines.append("")
        lines.append("**제안 액션** (승인하면 자동 실행됩니다)")
        for act in acts:
            label = ACTION_LABEL.get(act["type"], act["type"])
            status = act.get("status", "proposed")
            if status == "done" and act.get("result_path"):
                lines.append(f"- [{label}] {act['title']} — 실행 완료, 결과: `{act['result_path']}`")
            elif status == "failed":
                lines.append(f"- [{label}] {act['title']} — 실행 실패: {act.get('error', '')}")
            else:
                pr = PRIORITY_LABEL.get(act.get("priority", "later"), "")
                lines.append(f"- [{label}] {act['title']} ({pr}) — 승인: `igdm approve {act['id']}`")
                if act.get("detail"):
                    lines.append(f"  - {act['detail']}")
    lines.append("")
    return lines


def build_markdown(run: dict) -> str:
    stats = run.get("stats", {})
    items = run.get("items", [])
    threshold = run.get("min_usefulness_to_report", 40)
    main = [i for i in items if i["analysis"]["category"] in ("useful", "mixed") and i["analysis"]["usefulness_score"] >= threshold]
    rest = [i for i in items if i not in main]
    main.sort(key=lambda i: i["analysis"]["usefulness_score"], reverse=True)
    rest.sort(key=lambda i: i["analysis"]["usefulness_score"], reverse=True)

    lines = [f"# 인스타그램 DM 다이제스트 — {run.get('generated_at', '')}", ""]
    lines.append("## 요약")
    lines.append(f"- 읽은 대화방: {stats.get('threads_total', 0)}개 · 새 수신 메시지: {stats.get('new_messages', 0)}건 · 분석한 대화: {stats.get('analyzed', 0)}건")
    lines.append(f"- 유익/혼합(리포트 포함): {len(main)}건 · 유입·판매용/노이즈/기준 미달(제외): {len(rest)}건")
    if stats.get("skipped_old"):
        lines.append(f"- 기간 밖이거나 반응 메시지라 건너뜀: {stats['skipped_old']}건")
    if stats.get("deferred"):
        lines.append(f"- 이번 실행 상한(max_threads_per_run) 때문에 다음 실행으로 미룬 대화방: {stats['deferred']}개")
    if stats.get("errors"):
        lines.append(f"- 분석 오류: {stats['errors']}건 (아래 '오류' 참고)")
    if stats.get("tokens"):
        t = stats["tokens"]
        lines.append(f"- 토큰 사용: 입력 {t.get('input_tokens', 0):,} / 출력 {t.get('output_tokens', 0):,} / 캐시 읽기 {t.get('cache_read_input_tokens', 0):,}")
    lines.append("")

    pending = [a for a in run.get("actions", []) if a.get("status") == "proposed"]
    done = [a for a in run.get("actions", []) if a.get("status") == "done"]
    if pending or done:
        lines.append("## 승인 대기 액션")
        if pending:
            pending = sorted(pending, key=lambda a: PRIORITY_ORDER.get(a.get("priority", "later"), 2))
            for a in pending:
                pr = PRIORITY_LABEL.get(a.get("priority", "later"), "")
                lines.append(f"- `{a['id']}` [{ACTION_LABEL.get(a['type'], a['type'])}] {a['title']} ({pr}) ← {a.get('source', {}).get('sender', '')}")
            lines.append("")
            lines.append("승인: `igdm approve <id>` (여러 개 가능) · 거절: `igdm reject <id>` · 실행: `igdm act`")
        if done:
            lines.append("")
            lines.append("자동 실행된 액션:")
            for a in done:
                lines.append(f"- `{a['id']}` {a['title']} → `{a.get('result_path', '')}`")
        lines.append("")

    lines.append("## 유익한 DM")
    if main:
        for item in main:
            lines.extend(_render_item(item, full=True))
    else:
        lines.append("이번에는 리포트 기준을 넘는 유익한 DM 이 없었습니다.")
        lines.append("")

    if rest:
        lines.append("## 제외된 DM (유입·판매용, 노이즈, 기준 미달)")
        for item in rest:
            lines.extend(_render_item(item, full=False))

    if run.get("errors"):
        lines.append("## 오류")
        for err in run["errors"]:
            lines.append(f"- {err.get('thread_title', '')} ({err.get('sender', '')}): {err.get('error', '')}")
        lines.append("")

    if run.get("notes"):
        lines.append("## 참고")
        lines.extend(f"- {n}" for n in run["notes"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---- 최소 마크다운 → HTML 변환 (외부 의존성 없이 이메일용) --------------------------------

def _inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)
    return t


def md_to_html(md: str) -> str:
    out = ["<html><body style=\"font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;line-height:1.5;max-width:760px;margin:auto;padding:16px\">"]
    list_stack: list[int] = []  # 현재 열린 <ul> 의 들여쓰기 레벨

    def close_lists(to_level: int = -1):
        while list_stack and list_stack[-1] > to_level:
            list_stack.pop()
            out.append("</ul>")

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_lists()
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            continue
        m = re.match(r"^(\s*)-\s+(.*)$", line)
        if m:
            level = len(m.group(1)) // 2
            if not list_stack or list_stack[-1] < level:
                list_stack.append(level)
                out.append("<ul>")
            else:
                close_lists(level)
                if not list_stack:
                    list_stack.append(level)
                    out.append("<ul>")
            out.append(f"<li>{_inline(m.group(2))}</li>")
            continue
        close_lists()
        out.append(f"<p>{_inline(line)}</p>")
    close_lists()
    out.append("</body></html>")
    return "\n".join(out)
