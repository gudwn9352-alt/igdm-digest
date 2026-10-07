# 보류·미실행 항목 체크리스트 (2026-10-07 기준)

끝낸 항목은 `[x]` 로 바꾸세요. 이 파일은 Claude 와의 작업에서 "아직 안 한 것" 을 잊지 않기 위한 메모입니다.

## 사용자가 해야 하는 것

- [ ] **새 GitHub 저장소 만들기**: https://github.com/new 에서 `igdm-digest`, 비공개(Private), README 추가 끄기
- [ ] **Claude GitHub 앱에 새 저장소 접근 권한 주기**: https://github.com/apps/claude/installations/select_target
- [ ] 위 두 가지가 끝나면 Claude 에게 "만들었어" 라고 알리기 → Claude 가 `main` 으로 푸시
- [ ] (선택) 기존 `-_-` 저장소의 `claude/clever-pascal-v7n4ct` 브랜치 삭제 여부 결정
- [ ] `config.example.yaml` → `config.yaml` 복사 후 사업 프로필, Gmail 주소, `instagram.my_name` 채우기
- [ ] Claude API 키 발급 → 환경변수 `ANTHROPIC_API_KEY`
- [ ] Gmail 2단계 인증 켜고 앱 비밀번호 발급 → 환경변수 `GMAIL_APP_PASSWORD` → `igdm test-email` 로 확인
- [ ] 인스타그램 "내 정보 다운로드" 에서 메시지(JSON) 요청 (최대 48시간) → zip 내려받기
- [ ] 첫 실행: `igdm run --export 파일.zip --dry-run` → `--limit 5` 로 품질·비용 확인 → 전체 실행
- [ ] 첫 실행에서 오류가 나면 메시지를 Claude 에게 전달 (실제 Claude 호출, Gmail 발송, 웹 검색 액션은 아직 실제 계정으로 검증되지 않음)

## 보류 중인 결정

- [ ] **크롬으로 24시간마다 DM 직접 확인**: 클라우드 세션에서는 불가. 내 PC 의 Claude 데스크톱 앱(크롬 확장/내장 브라우저)에서만 가능하고 PC 가 켜져 있어야 함. 약관 위험도 있음. 하기로 하면 `--captured` JSON 입력으로 연결
- [ ] **강원 펜션 10곳 조사 + 제안 메일 초안**: Claude 가 만들어 줄 수 있음. 실제 발송은 초안 확인 후 한 건씩 승인
- [ ] **해외 Shopify**: Shopify Payments 한국 미지원(검색 기준) → 포트원/페이팔 등 결제 연동 계획 필요. 첫 주 수입 목표에서는 제외하고 4주 이상 과제로
- [ ] **릴스 수익화**: 첫 주 직접 수익은 0 으로 가정. 서비스 문의 유입 채널로 쓰는 전략으로 정리
- [ ] **"정확성·검증 우선 응답 원칙" 을 사용자 전역 CLAUDE.md 에 설치**: 클라우드 세션은 컨테이너가 사라져 전역 파일이 유지되지 않음. 내 PC 의 Claude Code 에서 `~/.claude/CLAUDE.md` 에 넣어야 함

## Claude 가 이어서 할 것 (사용자 신호 대기)

- [ ] 저장소 생성 확인 후 `igdm-digest` 푸시
- [ ] 요청 시 펜션 리드 조사·제안 메일 초안 작성
- [ ] 첫 실행 오류 수정
