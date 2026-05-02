import os
import requests
from dotenv import load_dotenv

load_dotenv()

TISTORY_ACCESS_TOKEN = os.environ.get("TISTORY_ACCESS_TOKEN", "")
TISTORY_BLOG_NAME = os.environ.get("TISTORY_BLOG_NAME", "")

API_BASE = "https://www.tistory.com/apis"


def post_article(title: str, content: str, tag: str = "주식,한국주식,주식분석") -> dict:
    """티스토리에 글 발행. 성공 시 {'ok': True, 'post_id': ..., 'url': ...} 반환"""

    if not TISTORY_ACCESS_TOKEN:
        raise ValueError(".env에 TISTORY_ACCESS_TOKEN이 없습니다.")
    if not TISTORY_BLOG_NAME:
        raise ValueError(".env에 TISTORY_BLOG_NAME이 없습니다.")

    params = {
        "access_token": TISTORY_ACCESS_TOKEN,
        "output": "json",
        "blogName": TISTORY_BLOG_NAME,
        "title": title,
        "content": content,
        "visibility": "3",  # 3 = 공개
        "tag": tag,
    }

    resp = requests.post(f"{API_BASE}/post/write", data=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    tistory = data.get("tistory", {})
    status = tistory.get("status", "")

    if status == "200":
        post_id = tistory.get("postId", "")
        url = tistory.get("url", "")
        return {"ok": True, "post_id": post_id, "url": url}
    else:
        return {"ok": False, "error": data}
