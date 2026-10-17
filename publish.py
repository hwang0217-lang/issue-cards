"""이미지 URL 목록을 인스타그램 카드뉴스(캐러셀)로 올린다. (Instagram 로그인 API)"""
import os
import time

import requests

API = "https://graph.instagram.com/v21.0"


def _check(resp: requests.Response) -> dict:
    data = resp.json()
    if resp.status_code != 200 or "error" in data:
        raise RuntimeError(f"인스타 API 오류: {data}")
    return data


def wait_until_ready(container_id: str, token: str, tries: int = 20) -> None:
    for _ in range(tries):
        r = requests.get(
            f"{API}/{container_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        )
        status = _check(r).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 처리 실패: {status}")
        time.sleep(3)
    raise TimeoutError("컨테이너 준비 시간이 너무 오래 걸려요")


def publish_carousel(image_urls: list[str], caption: str) -> str:
    token = os.environ["IG_ACCESS_TOKEN"]
    # 토큰 주인의 계정을 뜻하는 "me"를 쓰면 계정 ID를 잘못 넣어서 생기는 오류가 없어요.
    user_id = "me"

    child_ids = []
    for url in image_urls:
        r = requests.post(
            f"{API}/{user_id}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": token},
            timeout=60,
        )
        child_ids.append(_check(r)["id"])
    for cid in child_ids:
        wait_until_ready(cid, token)

    r = requests.post(
        f"{API}/{user_id}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": token,
        },
        timeout=60,
    )
    parent_id = _check(r)["id"]
    wait_until_ready(parent_id, token)

    r = requests.post(
        f"{API}/{user_id}/media_publish",
        data={"creation_id": parent_id, "access_token": token},
        timeout=60,
    )
    return _check(r)["id"]


def refresh_token() -> str:
    """장기 토큰을 60일 더 연장한다 (발급 후 24시간이 지나야 가능)."""
    token = os.environ["IG_ACCESS_TOKEN"]
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=30,
    )
    return _check(r)["access_token"]
