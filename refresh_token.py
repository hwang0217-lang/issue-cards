"""인스타 장기 토큰을 60일 더 연장하고, 새 토큰을 표준 출력(stdout)으로만 내보낸다.
토큰 값은 로그에 남지 않도록 워크플로가 변수에 담아 비밀 저장칸에 바로 넣는다."""
import os
import sys

import requests

r = requests.get(
    "https://graph.instagram.com/refresh_access_token",
    params={"grant_type": "ig_refresh_token", "access_token": os.environ["IG_ACCESS_TOKEN"]},
    timeout=30,
)
data = r.json()
if r.status_code != 200 or "access_token" not in data:
    # 토큰이 노출되지 않도록 오류 내용만 알린다
    print(f"토큰 갱신 실패: {data.get('error', data)}", file=sys.stderr)
    sys.exit(1)

days = int(data.get("expires_in", 0)) // 86400
print(f"토큰 갱신 성공: 앞으로 약 {days}일 사용 가능", file=sys.stderr)
print(data["access_token"])
