# 구직 플래너 (job-planner)

두 사람이 같이 쓰는 구직 플래너 웹앱. 공고·마감·전형 일정·할 일·자소서 답변과 문장 단위 댓글을 관리한다.

- `index.html` — 앱 화면 (GitHub Pages)
- `server/` — Google Apps Script 서버 코드 (데이터는 구글 시트, 공고 자동 정리는 Claude API)

비밀 값(앱 비밀번호, API 키, 시트 id, 서버 주소)은 이 저장소에 없다. 서버는 Apps Script 스크립트 속성에, 서버 주소는 각 기기에 저장된다.
