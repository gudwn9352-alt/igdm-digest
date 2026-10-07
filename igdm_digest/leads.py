"""웹 검색으로 영업 대상 업체(리드)를 찾는다. 공개된 사업자 연락처만 다루고, 연락은 사용자가 승인한 뒤에만 한다."""
from __future__ import annotations

from .analyze import ClaudeRunner, business_profile_text

LEADS_SYSTEM = """당신은 1인 온라인 서비스 사업자의 영업 리서처입니다. 웹 검색으로 제안 메일을 보낼 만한 업체를 찾아 정리합니다.

규칙:
- 업체의 공개된 사업 연락처(홈페이지, 대표 이메일, 대표 전화, 공식 SNS)만 기록한다. 개인의 사적인 연락처·개인정보는 수집하지 않는다.
- 검색으로 확인한 것과 추정을 구분한다. 확인하지 못한 항목은 "미확인" 으로 적는다.
- 각 업체마다 왜 적합한지(홈페이지가 없거나 낡음, 홍보 영상이 없음 등)를 근거 URL 과 함께 적는다.
- 결과는 한국어 마크다운. 마지막에 "다음 단계" 로 어떤 업체부터 어떤 제안을 보낼지 우선순위를 적는다.
"""


def find_leads(runner: ClaudeRunner, cfg: dict, brief: str, *, region: str | None = None, count: int = 10, max_uses: int = 10) -> dict:
    user = f"""## 내 사업
{business_profile_text(cfg)}

## 찾을 업체
{brief}
{('지역: ' + region) if region else ''}
목표 개수: {count}개 (확인된 것만, 억지로 채우지 말 것)

표 형식: | 업체명 | 지역 | 홈페이지(있음/없음/낡음 + URL) | 공개 연락처 | 적합한 이유(근거 URL) | 제안 포인트 |
"""
    return runner.web_research(LEADS_SYSTEM, user, max_uses=max_uses, label="leads")
