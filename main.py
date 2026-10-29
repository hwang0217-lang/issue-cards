"""매일 한 번 실행: 후보 수집 → 이슈 선정·점수 → 사실 기반 글 → 이미지 → 인스타 업로드.
단일 이슈가 어려우면 '오늘의 이슈 브리핑'으로 대신하고, 안전하게 다룰 이슈가 아예 없으면 그날은 발행하지 않는다."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect import collect
from publish import BlockedError, publish_carousel
from render import PHOTO_USED, render_all
from select_issue import propose_issues, rank_issues
from write_news import write_digest, write_news

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"posted": []}


GENERIC = {"논란", "발언", "발표", "시작", "확정", "이번", "오늘", "추진", "예고", "사과", "출범", "관련", "개최", "공개", "이슈", "결정"}


def _tokens(text: str) -> set:
    return {t for t in text.replace("'", " ").replace('"', " ").split() if len(t) >= 2 and t not in GENERIC}


def recently_posted(keyword: str, state: dict, days: int = 5) -> bool:
    """최근에 같은 이슈를 올렸는지. 키워드가 서로 포함되면 5일, 핵심 단어가 하나라도 겹치면 3일 동안 같은 이슈로 봐요
    (예: '부캉이 부산 열풍'과 '부캉이 바다로'가 번갈아 나오는 것을 막아요)."""
    now = datetime.now(KST)
    cut_same = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    cut_topic = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    mine = _tokens(keyword)
    for p in state["posted"]:
        day = p["at"][:10]
        if day >= cut_same and (keyword in p["keyword"] or p["keyword"] in keyword):
            return True
        if day >= cut_topic and mine & _tokens(p["keyword"]):
            return True
    return False


def blocked_now(state: dict) -> bool:
    until = state.get("blocked_until")
    return bool(until) and datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S") < until


def repo_prefix() -> str:
    """저장소 맨 위에서 이 파일이 있는 폴더까지의 경로 (맨 위에 있으면 빈 문자열)."""
    rel = ROOT.resolve().relative_to(Path.cwd().resolve()).as_posix()
    return "" if rel == "." else rel + "/"


def public_urls(paths: list) -> list:
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    prefix = repo_prefix()
    return [
        f"https://raw.githubusercontent.com/{repo}/{branch}/{prefix}{p.resolve().relative_to(ROOT.resolve()).as_posix()}"
        for p in paths
    ]


def wait_for_urls(urls: list, tries: int = 20) -> None:
    import requests

    for u in urls:
        for _ in range(tries):
            if requests.head(u, timeout=15).status_code == 200:
                break
            time.sleep(3)
        else:
            raise RuntimeError(f"이미지 주소가 열리지 않아요: {u}")


def commit_images() -> None:
    os.system("git config user.name 'cardnews-bot'")
    os.system("git config user.email 'cardnews-bot@users.noreply.github.com'")
    os.system(f"git add {repo_prefix()}images")
    os.system("git diff --cached --quiet || git commit -m 'add card images'")
    if os.system("git push") != 0:
        raise RuntimeError("이미지 push 실패")


def save_state(state: dict, used: list, title: str, media_id: str) -> None:
    at = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    for issue in used:  # 브리핑이면 다룬 이슈마다 기록해서 며칠간 다시 안 다뤄요
        state["posted"].append({
            "keyword": issue["keyword"], "title": title, "media_id": media_id,
            "score": issue["score"], "at": at,
        })
    state["posted"] = state["posted"][-200:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    if os.environ.get("NEWS_PAUSED") == "1":
        print("NEWS_PAUSED=1 이라서 발행하지 않아요 (긴급 정지).")
        return

    state = load_state()
    if blocked_now(state) and not DRY_RUN:
        print(f"인스타가 활동을 제한한 상태라서 {state['blocked_until']} 까지 쉬어요. (재시도하면 제한이 길어질 수 있어요)")
        return
    data = collect()
    issues = propose_issues(data["headlines"], data["trends"])
    print(f"AI가 고른 후보 이슈 {len(issues)}개")
    ranked = rank_issues(issues, data["headlines"], data["trends"], limit=8)
    fresh = [c for c in ranked if not recently_posted(c["keyword"], state)]

    # 1순위: 한 이슈를 깊게 (3~5장)
    content, used = None, []
    for cand in fresh:
        if cand["stats"]["outlet_count"] < 3:
            print(f"건너뜀(보도 언론사 3곳 미만): {cand['keyword']}")
            continue
        content, reason = write_news(cand)
        if content:
            used = [cand]
            print(f"선정: {cand['keyword']} (점수 {cand['score']}, 언론사 {cand['stats']['outlet_count']}곳)")
            break
        print(f"건너뜀({reason}): {cand['keyword']}")

    # 2순위: 단일 이슈가 어려우면 '오늘의 이슈 브리핑'으로 (이슈마다 한 장)
    if not content:
        pool = [c for c in fresh if c["stats"]["outlet_count"] >= 2][:5]
        if len(pool) >= 3:
            print(f"단일 이슈 대신 브리핑으로 전환: {', '.join(c['keyword'] for c in pool)}")
            content, reason = write_digest(pool)
            if content:
                used = pool
            else:
                print(f"브리핑도 건너뜀({reason})")

    if not content:
        print("오늘은 안전하게 다룰 수 있는 이슈가 없어서 발행하지 않아요.")
        return

    now = datetime.now(KST)
    date_text = f"{now:%Y.%m.%d} ({WEEKDAYS[now.weekday()]})"
    outlets = sorted({o for c in used for o in c["stats"]["outlets"]})

    slug = now.strftime("%Y%m%d-%H%M")
    paths = render_all(content, outlets, date_text, ROOT / "images" / slug)
    print(f"이미지 {len(paths)}장 생성 (AI 배경 이미지 사용: {'예' if PHOTO_USED['any'] else '아니오'})")

    notes = f"출처: {', '.join(outlets[:5])} 등 보도 종합\n※ 뉴스를 요약·정리한 게시물이에요. 정확한 내용은 각 언론사 원문 기사를 확인해 주세요."
    if PHOTO_USED["any"]:
        notes += "\n※ 배경 이미지는 AI가 만든 참고 이미지이며 실제 현장 사진이 아니에요."
    caption = "\n\n".join([content["caption"].strip(), notes, " ".join(content["hashtags"])])

    if DRY_RUN:
        print("DRY_RUN: 업로드하지 않고 종료\n")
        print(caption)
        return

    if os.environ.get("GEMINI_API_KEY") and not PHOTO_USED["any"]:
        # 배경 사진이 하나도 없는 카드는 눈에 안 띄어서 조회가 떨어져요. 올리지 않고 다음 실행에서 다시 시도해요.
        raise RuntimeError("AI 배경 이미지를 하나도 못 만들어서 발행을 건너뛰어요 (Gemini 결제 잔액·한도를 확인하세요)")

    commit_images()
    urls = public_urls(paths)
    wait_for_urls(urls)
    try:
        media_id = publish_carousel(urls, caption)
    except BlockedError as e:
        until = (datetime.now(KST) + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
        state["blocked_until"] = until
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"::warning::인스타가 이 계정의 활동을 제한했어요. 48시간({until}까지) 쉬어요.\n{e}")
        return
    state.pop("blocked_until", None)
    print(f"업로드 완료: {media_id}")
    save_state(state, used, content["cover_title"], media_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"실패: {e}", file=sys.stderr)
        raise
