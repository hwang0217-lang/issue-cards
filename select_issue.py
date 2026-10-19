"""후보 헤드라인을 이슈별로 묶고, '몇 곳의 언론사가 다뤘는지'로 화제성 점수를 매긴다. (외부 검색 API 없이 RSS만 사용)"""
import os
import re

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_HEADLINES = 300

# 코드에서 한 번 더 막는 민감 단어 (AI 판단과 별개로 항상 적용)
BLOCK_WORDS = [
    "자살", "극단적 선택", "극단선택", "유서", "성폭행", "성폭력", "성추행", "성착취", "성범죄", "불법촬영", "몰카",
    "살인", "살해", "시신", "변사", "사체", "아동학대", "학대", "흉기", "난동", "피살", "신상공개",
    "마약", "딥페이크 성",
]


def blocked_word(text: str):
    for w in BLOCK_WORDS:
        if w in text:
            return w
    return None


SYSTEM = """너는 '사회 이슈 카드뉴스' 인스타그램 계정의 편집자다.
번호가 붙은 헤드라인 목록을 읽고, 같은 사건·주제를 다룬 헤드라인끼리 묶어 '이슈' 목록을 만든다.

포함: 제도·정책 변화, 생활·물가·주거·노동·교육·교통·환경·안전·보건에 관한 이슈, 많은 사람에게 영향을 주는 사회 현상.
제외: 연예, 스포츠, 해외 국제 뉴스, 주식·코인 시황, 날씨 단신,
 정당·정치인 간 공방과 의혹, 선거, 개인이 특정되는 범죄·사고·재판, 자살, 성범죄, 미성년자·피해자가 나오는 사건,
 확정되지 않은 의혹이나 루머.
각 이슈에는 그 이슈를 다룬 헤드라인 번호(ids)를 빠짐없이 모두 적는다. 서로 다른 언론사가 같은 이슈를 다룰수록 중요한 이슈다.
서로 다른 이슈를 최대 10개까지만 고르고, 적합한 게 없으면 빈 목록을 낸다."""

TOOL = {
    "name": "submit_issues",
    "description": "묶은 사회 이슈 목록을 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "keyword": {"type": "string", "description": "2~3단어 명사구 (예: 소방 재정 개편)"},
                        "label": {"type": "string", "description": "이슈를 한 줄로 설명"},
                        "ids": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["keyword", "label", "ids"],
                },
            }
        },
        "required": ["issues"],
    },
}


def propose_issues(headlines: list, trends: list) -> list:
    pool = headlines[:MAX_HEADLINES]
    lines = [f"{i + 1}. {h['title']} ({h['outlet']})" for i, h in enumerate(pool)]
    prompt = ("헤드라인:\n" + "\n".join(lines) + "\n\n구글 급상승 검색어: " + ", ".join(trends)
              + "\n\n반드시 submit_issues 도구로만 제출해줘.")
    client = anthropic.Anthropic()
    for _ in range(3):
        msg = client.messages.create(
            model=MODEL, max_tokens=4500, system=SYSTEM, tools=[TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
        for b in msg.content:
            if b.type == "tool_use":
                return b.input.get("issues", [])
    return []


def _tokens(s: str) -> list:
    return [t for t in re.split(r"\s+", s.strip()) if len(t) >= 2]


def rank_issues(issues: list, headlines: list, trends: list, limit: int = 5) -> list:
    """점수 = 보도한 언론사 수 x3 + 헤드라인 수 + (구글 급상승 검색어와 겹치면 +5)."""
    pool = headlines[:MAX_HEADLINES]
    ranked = []
    for iss in issues:
        kw = iss["keyword"].strip()
        ids = sorted({i for i in iss.get("ids", []) if 1 <= i <= len(pool)})
        group = [pool[i - 1] for i in ids]
        if not group:
            continue
        text = " ".join([kw, iss.get("label", "")] + [h["title"] for h in group])
        word = blocked_word(text)
        if word:
            print(f"제외(민감어 '{word}'): {kw}")
            continue
        outlets = sorted({h["outlet"] for h in group})
        toks = _tokens(kw)
        trend_bonus = 5 if any(any(t in tr for t in toks) for tr in trends) else 0
        score = len(outlets) * 3 + len(group) + trend_bonus
        stats = {
            "keyword": kw, "articles": len(group), "outlet_count": len(outlets), "outlets": outlets,
            "samples": [{"outlet": h["outlet"], "title": h["title"], "description": h.get("description", "")}
                        for h in group[:14]],
        }
        ranked.append({**iss, "stats": stats, "trend_bonus": trend_bonus, "score": score})
        print(f"점수 {score:>4} | 언론사 {len(outlets):>2} | 헤드라인 {len(group):>3} | {kw}")
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:limit]
