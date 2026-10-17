"""수집한 기사 제목·요약(근거)만 사용해 사실 기반 카드뉴스 글을 쓴다. 불확실하면 발행하지 않는다."""
import os

import anthropic

from select_issue import blocked_word

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")

SYSTEM = """너는 '사회 이슈 카드뉴스' 인스타그램 계정의 작가다. 독자는 바쁜 20~40대다.
쉬운 말, 짧은 문장, 해요체로 쓰되 뉴스답게 차분하고 중립적인 어조를 유지한다.

[사실 규칙 - 가장 중요]
- 아래 '근거 기사' 목록에 적힌 내용만 쓴다. 목록에 없는 사실, 숫자, 날짜, 인물, 원인, 전망은 절대 만들지 않는다.
- 숫자와 날짜는 근거에 적힌 그대로 쓰고, 기사끼리 다르면 쓰지 말고 '보도마다 차이가 있어요'라고 한다.
- 단정하지 말고 '~라고 보도됐어요', '~라고 밝혔어요' 같은 전달 표현을 쓴다.
- 개인(일반인)의 이름·직장·신상은 쓰지 않는다. 공직자는 직책 위주로 쓴다.
- 누가 옳고 그른지 판단하지 않고, 논쟁이 있으면 양쪽 입장을 같은 비중으로 전한다. 의견·감정 표현 금지.
- 확정되지 않은 의혹, 수사·재판 중인 사건의 유무죄 암시, 범죄·사고 피해자, 미성년자, 자살, 성범죄는 다루지 않는다.
- 근거가 부족하거나 서로 모순되거나 위 금지 주제에 해당하면 can_publish를 false로 하고 skip_reason에 이유를 쓴다."""

TOOL = {
    "name": "submit_news",
    "description": "완성된 사회 이슈 카드뉴스를 제출한다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "can_publish": {"type": "boolean"},
            "skip_reason": {"type": "string"},
            "cover_title": {"type": "string"},
            "cover_sub": {"type": "string"},
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "highlight": {"type": "string"},
                    },
                    "required": ["title", "body", "highlight"],
                },
            },
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["can_publish"],
    },
}

PROMPT = """이슈: {label} (검색 키워드: {keyword})
최근 24시간 보도: 기사 {articles}건, 언론사 {outlet_count}곳

[근거 기사]
{facts}

submit_news 도구로 제출해줘.
- cover_title: 표지 제목 (최대 24자, 궁금증을 자극하되 과장·낚시 금지)
- cover_sub: 표지 부제 (최대 22자)
- slides: 정확히 5개, 순서대로 '무슨 일인가요 / 왜 이슈인가요 / 핵심 내용 / 영향은 / 앞으로는'
  각각 title(최대 16자), body(최대 70자, 근거에 있는 내용만), highlight(body에 글자 그대로 들어 있는 핵심 구절, 최대 14자)
  근거가 없는 슬라이드는 지어내지 말고, 그 경우 can_publish를 false로 해.
- caption: 설명글 (첫 줄은 핵심 한 문장, 3~5줄, 중립적, 마지막은 독자에게 의견을 묻는 가벼운 질문)
- hashtags: 8개, # 로 시작, 띄어쓰기 없이
한국어로 작성해줘."""


def _facts(stats: dict) -> str:
    lines = []
    for s in stats["samples"]:
        desc = s["description"][:160]
        lines.append(f"- [{s['outlet']}] {s['title']} — {desc}")
    return "\n".join(lines)


def write_news(issue: dict, tries: int = 2):
    stats = issue["stats"]
    prompt = PROMPT.format(
        label=issue.get("label", issue["keyword"]), keyword=issue["keyword"],
        articles=stats["articles"], outlet_count=stats["outlet_count"], facts=_facts(stats),
    )
    client = anthropic.Anthropic()
    for _ in range(tries):
        msg = client.messages.create(
            model=MODEL, max_tokens=2500, system=SYSTEM, tools=[TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
        for b in msg.content:
            if b.type != "tool_use":
                continue
            data = b.input
            if not data.get("can_publish"):
                return None, data.get("skip_reason", "AI가 발행 부적합으로 판단")
            problem = validate(data)
            if problem:
                print(f"검증 실패, 재시도: {problem}")
                break
            return data, ""
    return None, "글 생성/검증에 실패"


def validate(d: dict):
    for key in ("cover_title", "cover_sub", "slides", "caption", "hashtags"):
        if not d.get(key):
            return f"'{key}' 없음"
    if len(d["slides"]) != 5:
        return "slides는 5개여야 함"
    texts = [d["cover_title"], d["cover_sub"], d["caption"]]
    for s in d["slides"]:
        if not s.get("title") or not s.get("body"):
            return "slide 내용이 비어 있음"
        texts += [s["title"], s["body"]]
    word = blocked_word(" ".join(texts))
    if word:
        return f"민감어 '{word}' 포함"
    d["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in d["hashtags"]]
    return None
