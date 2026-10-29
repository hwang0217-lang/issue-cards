"""최근 게시물의 반응(좋아요·댓글·도달·저장·공유)을 insights.json에 모아 둔다. 실패해도 발행에는 영향 없음.
도달·저장·공유는 토큰에 인사이트 권한이 있을 때만 채워져요."""
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://graph.instagram.com/v21.0"
OUT = Path(__file__).parent / "insights.json"


def main() -> None:
    token = os.environ.get("IG_ACCESS_TOKEN")
    if not token:
        return
    r = requests.get(f"{API}/me/media", params={
        "fields": "id,timestamp,permalink,like_count,comments_count,media_type", "limit": 30, "access_token": token}, timeout=30)
    data = r.json()
    if "error" in data:
        print("인사이트 건너뜀:", data["error"].get("message"))
        return
    rows, note = [], ""
    for m in data.get("data", []):
        row = {k: m.get(k) for k in ("id", "timestamp", "permalink", "like_count", "comments_count")}
        ir = requests.get(f"{API}/{m['id']}/insights", params={"metric": "reach,saved,shares", "access_token": token}, timeout=30).json()
        if "data" in ir:
            for it in ir["data"]:
                row[it["name"]] = (it.get("values") or [{}])[0].get("value")
        elif not note:
            note = ir.get("error", {}).get("message", "")
        rows.append(row)
    OUT.write_text(json.dumps({"updated": time.strftime("%Y-%m-%d %H:%M:%S"), "insights_note": note, "posts": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"인사이트 {len(rows)}건 저장" + (f" (참고: {note})" if note else ""))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # 발행과 무관한 부가 기능이라 조용히 넘어간다
        print("인사이트 수집 실패:", e, file=sys.stderr)
