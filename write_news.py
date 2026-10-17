"""수집한 기사 제목·요약(근거)만 사용해 사실 기반 카드뉴스 글을 쓴다.
- 한 이슈로 3~5장을 쓰되, 근거가 부족하면 장 수를 줄인다.
- 단일 이슈가 어렵다면 '오늘의 이슈 브리핑'(여러 이슈를 한 장씩)으로 대신한다.
- 금지 주제(피해자·미성년자·자살·성범죄·미확정 의혹 등)는 어떤 경우에도 쓰지 않는다."""
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

[다루지 않는 주제 - can_publish를 false로 하고 skip_reason에 이유를 쓴다]
- 범죄·사고·재난의 피해자(사망자 조문·장례 포함), 미성년자, 자살, 성범죄, 확정되지 않은 의혹, 수사·재판 중 유무죄 암시.
- 근거가 서로 모순되어 사실을 확정할 수 없는 경우.
(근거가 짧거나 적은 것만으로는 거부하지 말고, 쓸 수 있는 내용만으로 장 수를 줄여서 쓴다.)"""

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
            "visual_style": {"type": "string"},
            "cover_image_prompt": {"type": "string"},
            "slides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "highlight": {"type": "string"},
                        "image_prompt": {"type": "string"},
                    },
                    "required": ["label", "title", "body", "highlight", "image_prompt"],
                },
            },
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["can_publish"],
    },
}

COMMON_FORMAT = """- cover_title: 표지 제목 (최대 24자, 궁금증을 자극하되 과장·낚시 금지)
- cover_sub: 표지 부제 (최대 22자)
- visual_style: 모든 배경 이미지가 공유할 분위기 한 줄 (영어, 예: "cool blue-gray tones, soft overcast light")
- cover_image_prompt: 표지 배경 이미지에 담을 '일반적인 장면이나 사물' 묘사 (영어 한두 문장)
- slides: {slide_rule}
  각각 label(최대 8자), title(최대 16자), body(최대 70자, 근거에 있는 내용만),
  highlight(body에 글자 그대로 들어 있는 핵심 구절, 최대 14자),
  image_prompt(그 장의 주제를 상징하는 일반적인 장면·사물 묘사, 영어 한두 문장)
- image_prompt 규칙: 실제 사건 현장, 특정 장소·건물·인물·얼굴·로고·글자·간판은 절대 묘사하지 않고,
  재난·사고·부상·시위·군중 장면도 쓰지 않는다. 대신 주제를 상징하는 평범한 사물이나 분위기를 쓴다.
  예) 비 소식 → "rain streaking down a window with softly blurred city lights"
      물가·경제 → "a calculator, coins and a notebook on a wooden desk"
      교육 → "empty wooden classroom desks in soft daylight"
      교통 → "a quiet road at dusk with blurred lights" (사고 장면 금지)
- caption: 설명글 (첫 줄은 핵심 한 문장, 3~5줄, 중립적, 마지막은 독자에게 의견을 묻는 가벼운 질문)
- hashtags: 8개, # 로 시작, 띄어쓰기 없이
한국어로 작성해줘."""

SINGLE_PROMPT = """이슈: {label} (검색 키워드: {keyword})
보도: 헤드라인 {articles}건, 언론사 {outlet_count}곳

[근거 기사]
{facts}

submit_news 도구로 제출해줘.
""" + COMMON_FORMAT.format(slide_rule=(
    "3~5개. label은 '무슨 일', '왜 이슈', '핵심', '영향', '앞으로' 중 근거가 있는 것만 골라 이 순서로 쓴다. "
    "근거가 없는 항목은 만들지 말고 장 수를 줄인다(최소 3개)."))

DIGEST_PROMPT = """오늘 가장 많은 언론이 다룬 사회 이슈 여러 개를 '오늘의 이슈 브리핑' 카드뉴스 한 편으로 묶어줘.
이슈 하나당 슬라이드 한 장이다.

{blocks}

submit_news 도구로 제출해줘.
""" + COMMON_FORMAT.format(slide_rule=(
    "3~5개, 이슈 하나당 한 장. label은 '이슈 1', '이슈 2'처럼, title은 이슈 이름, "
    "body는 그 이슈의 핵심 한두 문장(근거에 있는 내용만)."))


def _facts(stats: dict, limit: int = 14) -> str:
    lines = []
    for s in stats["samples"][:limit]:
        desc = s["description"][:160]
        lines.append(f"- [{s['outlet']}] {s['title']}" + (f" — {desc}" if desc else ""))
    return "\n".join(lines)


def _call(prompt: str, tries: int = 2):
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


def write_news(issue: dict, tries: int = 2):
    stats = issue["stats"]
    prompt = SINGLE_PROMPT.format(
        label=issue.get("label", issue["keyword"]), keyword=issue["keyword"],
        articles=stats["articles"], outlet_count=stats["outlet_count"], facts=_facts(stats),
    )
    return _call(prompt, tries)


def write_digest(issues: list, tries: int = 2):
    """단일 이슈로 못 쓸 때, 여러 이슈를 한 장씩 묶은 브리핑을 만든다."""
    blocks = []
    for n, iss in enumerate(issues, 1):
        st = iss["stats"]
        blocks.append(f"[이슈 {n}] {iss.get('label', iss['keyword'])} (언론사 {st['outlet_count']}곳)\n"
                      + _facts(st, limit=6))
    return _call(DIGEST_PROMPT.format(blocks="\n\n".join(blocks)), tries)


def validate(d: dict):
    for key in ("cover_title", "cover_sub", "slides", "caption", "hashtags"):
        if not d.get(key):
            return f"'{key}' 없음"
    if not 3 <= len(d["slides"]) <= 5:
        return "slides는 3~5개여야 함"
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
