#!/usr/bin/env bash
# src/ 조각을 합쳐 index.html 을 만든다:  bash build.sh
# 시험(가짜 서버, jsdom 필요):  node test/mock_server_test.js index.html
cd "$(dirname "$0")"
# 2026-11-25 은퇴: 이 주소(index.html·admin.html)는 '지원할게'로 옮겼다는 안내 페이지. 예전 앱을 다시 만들면 안내가 덮어써지므로 막아 둠
if [ "$1" != "--force-old-app" ]; then echo "구직 플래너는 은퇴했어요 (지원할게로 전환). 예전 앱을 굳이 만들려면: bash build.sh --force-old-app (index.html 이 안내 페이지 대신 예전 앱이 됨)"; exit 1; fi
{ cat src/1_head.html; cat src/2_base.css src/3_v12.css src/4_app.css; echo "</style>"; echo "</head>"; echo "<body>"; cat src/5_body.html; echo "</body>"; echo "</html>"; } > index.html
echo "index.html 생성 완료"
