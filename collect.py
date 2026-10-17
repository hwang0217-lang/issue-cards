"""공개 RSS 피드(언론사가 헤드라인 공유용으로 내놓는 피드)에서 오늘의 뉴스 후보와 구글 급상승 검색어를 모은다."""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; cardnews-bot/1.0)"}
PER_FEED_LIMIT = 40

# (피드 이름, 주소, 고정 언론사명 - 구글 뉴스처럼 제목에 언론사가 붙는 피드는 빈 문자열)
HEADLINE_FEEDS = [
    ("구글뉴스 주요", "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", ""),
    ("구글뉴스 국내", "https://news.google.com/rss/headlines/section/topic/NATION?hl=ko&gl=KR&ceid=KR:ko", ""),
    ("연합뉴스", "https://www.yna.co.kr/rss/society.xml", "연합뉴스"),
    ("SBS", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER", "SBS"),
    ("경향신문", "https://www.khan.co.kr/rss/rssdata/society_news.xml", "경향신문"),
    ("조선일보", "https://www.chosun.com/arc/outboundfeeds/rss/category/national/?outputType=xml", "조선일보"),
    ("동아일보", "https://rss.donga.com/national.xml", "동아일보"),
    ("노컷뉴스", "https://rss.nocutnews.co.kr/nocutnews.xml", "노컷뉴스"),
    ("오마이뉴스", "http://rss.ohmynews.com/rss/ohmynews.xml", "오마이뉴스"),
    ("서울신문", "https://www.seoul.co.kr/xml/rss/rss_society.xml", "서울신문"),
    ("세계일보", "https://www.segye.com/Articles/RSSList/segye_society.xml", "세계일보"),
    ("뉴시스", "https://www.newsis.com/RSS/society.xml", "뉴시스"),
    ("한겨레", "https://www.hani.co.kr/rss/society/", "한겨레"),
]
TRENDS_FEED = "https://trends.google.com/trending/rss?geo=KR"


def normalize_outlet(name: str) -> str:
    name = " ".join(name.split())
    m = re.match(r"^(KBS|MBC|SBS|JTBC|YTN|MBN)\s*뉴스$", name)
    return m.group(1) if m else name


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el, name: str) -> str:
    for c in el:
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def _clean(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


def _parse_time(s: str):
    try:
        dt = parsedate_to_datetime(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone(timedelta(hours=9)))
    except Exception:
        return None


def _fetch(url: str) -> ET.Element:
    r = requests.get(url, headers=UA, timeout=25, allow_redirects=True)
    r.raise_for_status()
    return ET.fromstring(r.content)


def collect(hours: int = 36) -> dict:
    now = datetime.now(timezone.utc)
    seen, headlines, ok_feeds = set(), [], 0
    for name, url, fixed_outlet in HEADLINE_FEEDS:
        try:
            root = _fetch(url)
        except Exception as e:
            print(f"피드 실패({name}): {e}")
            continue
        count = 0
        for item in root.iter("item"):
            title = _clean(_child_text(item, "title"))
            outlet = fixed_outlet
            if not outlet and " - " in title:  # 구글 뉴스: '제목 - 언론사'
                title, outlet = title.rsplit(" - ", 1)
            outlet = normalize_outlet(outlet)
            if not title or not outlet or title in seen:
                continue
            published = _parse_time(_child_text(item, "pubDate"))
            if published and now - published > timedelta(hours=hours):
                continue
            desc = "" if name.startswith("구글") else _clean(_child_text(item, "description"))[:200]
            seen.add(title)
            headlines.append({"title": title, "outlet": outlet, "description": desc,
                              "feed": name, "published": published})
            count += 1
            if count >= PER_FEED_LIMIT:
                break
        if count:
            ok_feeds += 1

    trends = []
    try:
        for item in _fetch(TRENDS_FEED).iter("item"):
            kw = _child_text(item, "title")
            if kw:
                trends.append(kw)
    except Exception as e:
        print(f"구글 트렌드 실패: {e}")

    if len(headlines) < 30 or ok_feeds < 4:
        raise RuntimeError(f"뉴스 후보가 너무 적어요(기사 {len(headlines)}개, 피드 {ok_feeds}곳). 피드 접속을 확인해 주세요.")
    print(f"뉴스 후보 {len(headlines)}개 (피드 {ok_feeds}곳), 급상승 검색어 {len(trends)}개")
    return {"headlines": headlines, "trends": trends}


if __name__ == "__main__":
    data = collect()
    outlets = sorted({h["outlet"] for h in data["headlines"]})
    print("언론사:", ", ".join(outlets))
    for h in data["headlines"][:8]:
        print(f"- [{h['outlet']}] {h['title']}")
