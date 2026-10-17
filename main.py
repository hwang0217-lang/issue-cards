"""매일 한 번 실행: 후보 수집 → 이슈 선정·점수 → 사실 기반 글 → 이미지 → 인스타 업로드.
불확실하거나 위험하면 그날은 발행하지 않는다."""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect import collect
from publish import publish_carousel
from render import render_all
from select_issue import propose_issues, rank_issues
from write_news import write_news

ROOT = Path(__file__).parent
STATE_FILE = ROOT / "state.json"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
KST = timezone(timedelta(hours=9))
WEEKDAYS = "월화수목금토일"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"posted": []}


def recently_posted(keyword: str, state: dict, days: int = 5) -> bool:
    """최근 며칠 안에 같은 이슈를 올렸는지 (키워드가 서로 포함되면 같은 이슈로 본다)."""
    cutoff = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")
    for p in state["posted"]:
        if p["at"][:10] >= cutoff and (keyword in p["keyword"] or p["keyword"] in keyword):
            return True
    return False


def public_urls(paths: list) -> list:
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return [
        f"https://raw.githubusercontent.com/{repo}/{branch}/cardnews/{p.relative_to(ROOT).as_posix()}"
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
    os.system("git add cardnews/images")
    os.system("git diff --cached --quiet || git commit -m 'add card images'")
    if os.system("git push") != 0:
        raise RuntimeError("이미지 push 실패")


def save_state(state: dict, issue: dict, title: str, media_id: str) -> None:
    state["posted"].append({
        "keyword": issue["keyword"], "title": title, "media_id": media_id,
        "score": issue["score"], "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
    })
    state["posted"] = state["posted"][-200:]
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    if os.environ.get("NEWS_PAUSED") == "1":
        print("NEWS_PAUSED=1 이라서 발행하지 않아요 (긴급 정지).")
        return

    state = load_state()
    data = collect()
    issues = propose_issues(data["headlines"], data["trends"])
    print(f"AI가 고른 후보 이슈 {len(issues)}개")
    ranked = rank_issues(issues, data["headlines"], data["trends"])

    chosen, content = None, None
    for cand in ranked:
        if recently_posted(cand["keyword"], state):
            print(f"건너뜀(최근에 올린 이슈): {cand['keyword']}")
            continue
        if cand["stats"]["outlet_count"] < 3:
            print(f"건너뜀(보도 언론사 3곳 미만): {cand['keyword']}")
            continue
        content, reason = write_news(cand)
        if content:
            chosen = cand
            break
        print(f"건너뜀({reason}): {cand['keyword']}")

    if not chosen:
        print("오늘은 안전하게 다룰 수 있는 이슈가 없어서 발행하지 않아요.")
        return

    print(f"선정: {chosen['keyword']} (점수 {chosen['score']}, 언론사 {chosen['stats']['outlet_count']}곳)")
    now = datetime.now(KST)
    date_text = f"{now:%Y.%m.%d} ({WEEKDAYS[now.weekday()]})"
    outlets = chosen["stats"]["outlets"]

    caption = "\n\n".join([
        content["caption"].strip(),
        f"출처: {', '.join(outlets[:5])} 등 보도 종합\n※ 뉴스를 요약·정리한 게시물이에요. 정확한 내용은 각 언론사 원문 기사를 확인해 주세요.",
        " ".join(content["hashtags"]),
    ])

    slug = now.strftime("%Y%m%d-%H%M")
    paths = render_all(content, outlets, date_text, ROOT / "images" / slug)
    print(f"이미지 {len(paths)}장 생성")

    if DRY_RUN:
        print("DRY_RUN: 업로드하지 않고 종료\n")
        print(caption)
        return

    commit_images()
    urls = public_urls(paths)
    wait_for_urls(urls)
    media_id = publish_carousel(urls, caption)
    print(f"업로드 완료: {media_id}")
    save_state(state, chosen, content["cover_title"], media_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"실패: {e}", file=sys.stderr)
        raise
