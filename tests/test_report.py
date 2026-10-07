from igdm_digest.report import build_markdown, md_to_html


def _run():
    return {
        "generated_at": "2026-10-07 09:00",
        "min_usefulness_to_report": 40,
        "stats": {"threads_total": 4, "new_messages": 4, "analyzed": 3, "skipped_old": 2, "deferred": 0, "errors": 1,
                  "tokens": {"input_tokens": 1234, "output_tokens": 56, "cache_read_input_tokens": 0}},
        "items": [
            {"thread_title": "김정보", "sender": "김정보", "received": "2026-09-30", "links": [{"url": "https://example.com/a", "status": "ok"}],
             "analysis": {"category": "useful", "usefulness_score": 82, "funnel_score": 15, "topic": "쇼피파이 체크리스트", "verdict": "바로 씀",
                          "summary": "요약문", "key_points": ["포인트1"], "red_flags": [],
                          "business_fit": [{"business": "쇼핑몰", "fit_score": 85, "how_to_apply": "적용", "expected_value": "효과", "effort": "medium"}],
                          "proposed_actions": []},
             "actions": [{"id": "abcd1234", "type": "outreach_email", "title": "제안 메일", "detail": "강원 펜션", "status": "proposed", "priority": "this_week"},
                         {"id": "ef567890", "type": "checklist", "title": "체크리스트", "status": "done", "result_path": "data/deliverables/x.md"}]},
            {"thread_title": "박강의", "sender": "박강의", "received": "2026-10-02", "links": [],
             "analysis": {"category": "funnel", "usefulness_score": 10, "funnel_score": 95, "topic": "무료 특강", "verdict": "유도",
                          "summary": "", "key_points": [], "red_flags": ["선착순"], "business_fit": [], "proposed_actions": []},
             "actions": []},
        ],
        "actions": [{"id": "abcd1234", "type": "outreach_email", "title": "제안 메일", "status": "proposed", "priority": "this_week", "source": {"sender": "김정보"}},
                    {"id": "zz", "type": "checklist", "title": "나중", "status": "proposed", "priority": "later", "source": {"sender": "김정보"}},
                    {"id": "ef567890", "type": "checklist", "title": "체크리스트", "status": "done", "result_path": "data/deliverables/x.md"}],
        "errors": [{"thread_title": "최요청", "sender": "최요청", "error": "ClaudeError: boom"}],
        "notes": ["참고 메모"],
    }


def test_markdown_sections_and_ordering():
    md = build_markdown(_run())
    assert md.startswith("# 인스타그램 DM 다이제스트 — 2026-10-07 09:00")
    assert "## 승인 대기 액션" in md and "igdm approve abcd1234" in md
    assert md.index("`abcd1234`") < md.index("`zz`")  # 이번 주 현금화가 먼저
    assert "이번 주 현금화" in md
    assert "## 유익한 DM" in md and "### 쇼피파이 체크리스트 — 김정보 (2026-09-30)" in md
    assert "**내 사업에 적용하면**" in md and "쇼핑몰 (적합도 85" in md
    assert "실행 완료, 결과: `data/deliverables/x.md`" in md
    assert "## 제외된 DM" in md and "무료 특강 — 박강의" in md and "주의 신호: 선착순" in md
    assert "## 오류" in md and "boom" in md and "## 참고" in md
    assert "토큰 사용: 입력 1,234" in md


def test_md_to_html_basic_structure():
    html = md_to_html("# 제목\n\n- 항목 **굵게** `코드` https://a.b/c\n  - 하위\n\n문단\n")
    assert "<h1>제목</h1>" in html
    assert "<ul>" in html and "<strong>굵게</strong>" in html and "<code>코드</code>" in html
    assert '<a href="https://a.b/c">' in html and "<p>문단</p>" in html
    assert html.count("<ul>") == html.count("</ul>") == 2
