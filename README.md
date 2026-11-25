# 구직 플래너 (job-planner)

> **2026-11-25 은퇴 — '지원할게'(https://iwillapply.kms2086.workers.dev, 코드 `../job-planner-cf/`)로 전환.** 이 주소는 이동 안내 페이지(`index.html`·`admin.html`), 서버는 읽기만 받음(`MOVED_TO`). `src/`·`server/` 는 기록으로 남김. `tools/`(자소서 올리기·공고 폴더 정리)는 계속 쓰며 지원할게 서버에 저장함.

취업 준비용 웹앱. 공고·마감·전형 일정·할 일·자소서 문항과 답변, 문장 단위 댓글을 관리한다. 구글 계정으로 로그인하고, 플래너를 다른 사람에게 노션처럼 공유(댓글 허용 · 읽기 허용)할 수 있다.

- `index.html` — 앱 화면 (GitHub Pages). `src/` 조각을 `bash build.sh` 로 합쳐 만든다
- `admin.html` — 관리자 콘솔 (가입 승인·사람별 하루 한도·플래너 주인 지정)
- `server/` — Google Apps Script 서버 (데이터는 구글 시트, 공고 자동 정리는 Claude API)
- `tools/jaso_sync.py` — 자소서 MD 를 플래너에 올리는 도구 (도구 키 사용)
- `test/` — 자동 시험 (`npm test`), 화면 미리보기·사진 도구
- `AGENTS.md` — 코드 리뷰 에이전트용 안내

비밀 값(API 키·세션 서명 값·시트 id·도구 키)은 이 저장소에 없다. 서버는 Apps Script 스크립트 속성과 `server/Local.gs`(제외 파일)에, 배포 정보·도구 키는 `config.local.json`(제외 파일)에 있다.

2026-11-22: 비밀번호 방식 앱을 구글 로그인 버전(job-planner-login 시험판)으로 통합. 데이터 시트는 그대로 쓴다.
