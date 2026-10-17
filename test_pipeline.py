"""키 없이 돌려보는 점검용 스크립트: 실제 RSS 수집 + 가짜 AI 응답으로 점수·필터·검증·이미지까지 확인한다."""
import json
from pathlib import Path

import collect
import select_issue
import write_news
from render import render_all

# 1) 실제 RSS 수집 (키 필요 없음)
data = collect.collect()
heads = data["headlines"]

# 2) 가짜 이슈 묶음으로 점수 계산과 민감어 필터 확인 (실제 헤드라인 번호 사용)
def ids_with(word):
    return [i + 1 for i, h in enumerate(heads[:select_issue.MAX_HEADLINES]) if word in h["title"]]

safe = [i for i in ids_with("") if not select_issue.blocked_word(heads[i - 1]["title"])]
common = safe[:12]                            # 민감어가 없는 여러 언론사 헤드라인 12개를 한 이슈로 가정
few = safe[12:14]
issues = [
    {"keyword": "테스트 이슈 가", "label": "여러 곳이 다룬 이슈", "ids": common},
    {"keyword": "테스트 이슈 나", "label": "적게 다룬 이슈", "ids": few},
    {"keyword": "인천 흉기 난동", "label": "사건", "ids": common[:3]},
    {"keyword": "자살 예방 대책", "label": "정책", "ids": common[3:6]},
]
ranked = select_issue.rank_issues(issues, heads, data["trends"])
names = [r["keyword"] for r in ranked]
assert names[0] == "테스트 이슈 가" and "인천 흉기 난동" not in names and "자살 예방 대책" not in names, names
print("점수 순위와 민감어 제외: OK ->", names)

# 3) 글 검증 로직 확인 (민감어가 들어간 글은 거부되어야 함)
good = json.loads(Path("sample.json").read_text(encoding="utf-8"))
good["caption"], good["hashtags"] = "중립적인 설명글이에요.\n의견을 남겨 주세요.", ["사회이슈", "#뉴스"]
assert write_news.validate(good) is None and good["hashtags"][0] == "#사회이슈"
bad = json.loads(json.dumps(good, ensure_ascii=False))
bad["slides"][0]["body"] = "흉기 난동이 있었다고 보도됐어요."
assert write_news.validate(bad) is not None
print("글 검증(민감어 거부): OK")

# 4) 이미지 렌더링
paths = render_all(good, ["연합뉴스", "KBS", "한겨레"], "2026.10.17 (토)", Path("out_sample"))
print("이미지", len(paths), "장 생성: OK")
