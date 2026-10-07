# igdm-digest — 인스타그램 DM 다이제스트

인스타그램에서 받은 DM(정보성 릴스에 댓글을 남기면 자동으로 오는 메시지 등)을 모아서

1. **유익한 정보인지, 강의 판매·플랫폼 유입용 미끼인지** 판별하고
2. 유익한 것만 **요약**하고
3. **내 사업에 어떻게 적용할지** 제안하고
4. 승인하면 **실제 산출물(체크리스트, 영상 기획안, 실험 설계, 영업 대상 업체 목록, 제안 메일 초안)을 만들어 주는**

자동화 도구입니다. 결과는 Gmail(또는 파일/콘솔)로 받습니다.

```
인스타그램 '내 정보 다운로드' (zip)  ──▶  igdm run  ──▶  Gmail 리포트
   또는 브라우저로 수집한 JSON              │
                                           ├─ 유익 / 혼합 / 유입·판매용 / 노이즈 분류 + 점수
                                           ├─ 링크(노션·블로그 등) 본문까지 읽어서 요약
                                           ├─ 사업 라인별 적용안 + 액션 제안 (이번 주 현금화 우선)
                                           └─ data/actions.json 에 액션 저장 → igdm approve → igdm act
```

## 왜 '내보내기' 방식인가

- 인스타그램 **공식 Messaging API** 는 프로페셔널(비즈니스/크리에이터) 계정 + Meta 개발자 앱 등록이 필요하고, 개인 계정은 쓸 수 없습니다.
- 비공식 API·세션 쿠키 스크래핑은 Meta 약관 위반이라 계정 정지 위험이 있어 이 도구는 지원하지 않습니다.
- **'내 정보 다운로드'** 는 계정 종류와 상관없이 전체 DM 을 JSON 으로 받을 수 있고 차단 위험이 없습니다. 대신 요청 후 최대 48시간이 걸리고 수동이라, 주 1회 정도 돌리는 배치 방식에 맞습니다.
- 브라우저(크롬 확장 등)로 받은 메시지를 직접 긁어 둔 경우를 위해 간단한 **수집 JSON 입력**도 지원합니다 (`--captured`). 자세한 형식은 아래 참고.

## 설치

```bash
git clone <이 저장소>
cd <저장소>
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp config.example.yaml config.yaml
```

Python 3.10 이상이 필요합니다.

## 준비물 3가지

### 1) 인스타그램 DM 내보내기

1. 인스타그램 앱 → 프로필 → ≡ → **내 활동** → **내 정보 다운로드** (또는 계정 센터 → 내 정보 및 권한 → 내 정보 다운로드)
2. **일부 정보 → 메시지** 선택, 형식은 **JSON**, 기간은 필요한 만큼
3. 메일로 링크가 오면(최대 48시간) zip 을 내려받아 아무 폴더에 둡니다. 압축을 풀지 않아도 됩니다.

### 2) Claude API 키

[Claude Console](https://platform.claude.com/) 에서 API 키를 만들고 환경변수로 넣습니다.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### 3) Gmail 앱 비밀번호 (리포트를 Gmail 로 받으려면)

1. Google 계정 → 보안 → **2단계 인증** 켜기
2. 보안 → **앱 비밀번호** → 이름을 아무거나 넣고 생성 → 16자리 값 복사
3. 환경변수로 넣습니다 (파일에 쓰지 마세요).

```bash
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

`config.yaml` 의 `delivery.gmail.from` 에 내 Gmail, `to` 에 받을 주소를 적습니다. 설정이 맞는지 확인:

```bash
igdm test-email
```

나중에 Gmail 대신 파일로 받고 싶으면 `delivery.method` 를 `file` 로 바꾸면 됩니다.

## config.yaml 채우기

`business` 블록이 분석 품질을 좌우합니다. 현재 하는 일, 이번 주 목표, 사업 라인, 제약을 솔직하게 적어 두면 Claude 가 그 기준으로 "이 DM 이 나한테 돈이 되는 정보인가" 를 판단합니다. 예시는 `config.example.yaml` 에 있습니다.

| 키 | 설명 |
|---|---|
| `instagram.my_name` | 내 인스타그램 이름. 비우면 모든 대화방에 공통으로 등장하는 참가자를 나로 자동 감지 |
| `analysis.since_days` | 처음 실행 때 수년치를 전부 분석하지 않도록 최근 N일만 (기본 60, 0이면 전체) |
| `analysis.max_threads_per_run` | 한 번에 분석할 최대 대화방 수(비용 상한). 넘치면 다음 실행으로 미룸 |
| `analysis.fetch_links` | DM 안의 링크 본문을 가져와 함께 분석 (인스타·페이스북 링크는 로그인 벽 때문에 생략) |
| `analysis.min_usefulness_to_report` | 이 점수 미만은 리포트에서 한 줄로만 집계 |
| `delivery.method` | `gmail` / `file` / `stdout` |
| `actions.auto_execute` | 승인 없이 자동 실행할 액션 유형 (예: `[checklist, content_brief]`). **메일 발송은 어떤 설정으로도 자동 실행되지 않음** |

## 사용법

```bash
# 1) 무엇을 분석할지 미리보기 (Claude 호출 없음, 비용 0)
igdm run --export ~/Downloads/instagram-xxx.zip --dry-run

# 2) 실제 실행: 분석 → 리포트 → Gmail 전송
igdm run --export ~/Downloads/instagram-xxx.zip

# 3) 리포트에 적힌 액션 승인 → 실행 (산출물은 data/deliverables/ 에 .md 로 저장)
igdm actions                       # 목록
igdm approve a1b2c3d4 e5f6a7b8     # 승인
igdm act                           # 승인된 것 실행
igdm approve a1b2c3d4 --run        # 승인과 동시에 실행

# 4) 제안 메일 초안은 내용을 확인한 뒤 명시적으로만 발송
igdm send a1b2c3d4 --to owner@pension.com          # 미리보기만
igdm send a1b2c3d4 --to owner@pension.com --yes    # 실제 발송

# 5) 영업 대상 업체 찾기 (DM 과 무관하게 바로)
igdm leads "홈페이지가 없거나 낡은 펜션" --region 강원 --count 10

# 기타
igdm report            # 마지막 리포트 다시 보기
igdm report --deliver  # 다시 전송
```

새 내보내기 파일로 다시 실행하면 **이미 처리한 메시지는 건너뛰고** 새 메시지만 분석합니다 (`data/state.json`).

### 액션 유형

| 유형 | 산출물 | 외부 영향 |
|---|---|---|
| `checklist` | 단계별 실행 체크리스트 | 없음 |
| `content_brief` | 릴스/홍보 영상 기획안 + AI 영상 도구용 프롬프트 초안 | 없음 |
| `experiment` | 쇼핑몰 등에 적용할 실험 설계서 | 없음 |
| `research` | 웹 검색을 곁들인 조사 메모 | 없음 (검색만) |
| `lead_search` | 웹 검색으로 찾은 영업 대상 업체 표 (공개 사업 연락처만) | 없음 (검색만) |
| `outreach_email` | 업체에 보낼 제안 메일 **초안** | `igdm send ... --yes` 를 직접 실행할 때만 발송 |

### 24시간마다 자동 실행하기

내보내기 자체는 인스타그램이 수동으로만 제공하므로, "zip 을 받아 특정 폴더에 넣는 것" 까지는 사람이 해야 합니다. 그 뒤는 cron 으로 자동화할 수 있습니다.

```cron
# 매일 09:00, 폴더의 가장 최근 zip 으로 실행
0 9 * * * cd /path/to/repo && . .venv/bin/activate && igdm run --export "$(ls -t ~/igdm-exports/*.zip | head -1)" >> data/cron.log 2>&1
```

### 브라우저로 수집한 메시지 넣기 (`--captured`)

Claude 데스크톱 앱 + 크롬 확장(Claude in Chrome) 처럼 로그인된 브라우저를 다룰 수 있는 환경에서 받은편지함을 읽어 아래 형식으로 저장하면, 내보내기 없이도 같은 파이프라인을 돌릴 수 있습니다.

```json
[
  {"thread": "김정보", "sender": "김정보", "timestamp": "2026-10-06T10:00:00+09:00",
   "text": "요청하신 자료입니다 https://example.com/doc", "links": ["https://example.com/doc"]},
  {"thread": "김정보", "sender": "나", "timestamp": "2026-10-06T10:01:00+09:00", "text": "감사합니다", "from_me": true}
]
```

```bash
igdm run --captured captured.json
```

주의: 브라우저 자동화로 본인 계정을 읽는 것도 Meta 약관상 "자동화된 접근" 에 해당할 수 있습니다. 공식 내보내기가 가장 안전합니다.

## 리포트 예시 구조

```
# 인스타그램 DM 다이제스트 — 2026-10-07 09:00
## 요약                 읽은 대화방 / 새 메시지 / 분석 / 제외 / 토큰
## 승인 대기 액션        `id` [유형] 제목 (이번 주 현금화 / 이달 안 / 기반 작업)
## 유익한 DM            제목 — 보낸 사람 (날짜) · 분류·점수 · 한 줄 판단 · 요약 · 핵심 포인트 · 주의 신호
                         · 내 사업에 적용하면 · 링크 · 제안 액션
## 제외된 DM            유입·판매용 / 노이즈 / 기준 미달 — 한 줄씩
## 오류 / 참고
```

## 안전장치

- DM 과 링크 본문은 "데이터" 로만 취급하고 그 안의 지시를 따르지 않도록 프롬프트에 명시했습니다.
- 제안 메일은 초안까지만 자동이며, 발송은 `--yes` 를 붙인 명령을 사람이 직접 실행할 때만 이루어집니다. 초안에 `{자리표시자}` 가 남아 있으면 발송을 막습니다.
- 영업 대상 업체 조사는 공개된 사업 연락처만 기록하도록 지시합니다.
- `config.yaml`, `data/` 는 `.gitignore` 에 있어 개인 정보가 저장소에 올라가지 않습니다.

## 비용 감

Claude Opus 5.5 기준 입력 $4 / 출력 $20 (100만 토큰당). DM 하나 분석에 보통 입력 3~8천 토큰(링크 본문 포함), 출력 1~2천 토큰이 들어 **DM 1건당 대략 20~60원** 수준입니다. 시스템 프롬프트는 캐시되어 두 번째 호출부터 입력 비용이 줄어듭니다. `analysis.model` 을 `claude-sonnet-5-5` 로 바꾸면 절반 가격이지만 판단 품질은 조금 낮아질 수 있습니다. 실제 사용량은 실행 후 출력되는 토큰 집계로 확인하세요.

## 검증된 것 / 검증하지 못한 것

이 저장소를 만든 환경에는 Claude API 키와 Gmail 계정이 없어서, 다음은 **가짜 응답으로만** 테스트했습니다. 처음 실행할 때 확인이 필요합니다.

- 실제 Claude 호출 (요청 형식은 공식 SDK 1.11 시그니처로 검증. 서버측 폴백·구조화 출력이 400 으로 거부되면 자동으로 단순한 요청으로 재시도함)
- 실제 Gmail SMTP 발송 (`igdm test-email` 로 확인)
- 웹 검색 도구(`web_search_20260209`) 를 쓰는 `research` / `lead_search` / `igdm leads`

내보내기 파싱(한글 깨짐 복구, 페이지 병합, zip, 메시지 요청함, 반응 메시지 제외, 중복 처리), 리포트 생성, 파일 전달, 액션 저장·승인·실행 흐름은 `pytest` 로 검증했습니다.

```bash
pytest -q
```

## 문제 해결

- **한글이 `ì•ˆë…•` 처럼 깨져 보임** → 내보내기 원본 특성이며 도구가 자동으로 복구합니다. 그래도 깨지면 이슈로 알려주세요.
- **"내 이름을 자동 감지하지 못했습니다"** → `instagram.my_name` 에 인스타그램 표시 이름을 적으세요. 대화방이 1개뿐이면 자동 감지가 안 됩니다.
- **Gmail 발송 실패** → 2단계 인증과 앱 비밀번호가 맞는지, `from` 이 앱 비밀번호를 만든 계정인지 확인. 실패해도 리포트는 `data/reports/` 에 저장됩니다.
- **첫 실행 비용이 걱정됨** → `--dry-run` 으로 건수를 보고, `--limit 5` 로 조금만 돌려 품질을 확인한 뒤 전체를 실행하세요.
