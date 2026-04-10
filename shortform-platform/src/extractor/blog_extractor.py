"""
블로그/웹페이지 콘텐츠 추출 모듈
URL 또는 직접 입력한 텍스트에서 본문을 추출합니다.
"""

import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup


@dataclass
class BlogContent:
    title: str
    text: str
    url: str


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# 본문과 무관한 태그
_SKIP_TAGS = ["script", "style", "nav", "footer", "header", "aside",
              "form", "noscript", "iframe", "svg", "button"]


def extract(url: str = "", text: str = "") -> BlogContent:
    """
    블로그 콘텐츠를 추출합니다.

    Args:
        url:  블로그 URL (우선 사용)
        text: 직접 입력한 텍스트 (url 없을 때 사용)

    Returns:
        BlogContent(title, text, url)
    """
    if url:
        return _scrape(url)
    return BlogContent(title="블로그 글", text=text.strip(), url="")


def _scrape(url: str) -> BlogContent:
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    # 제목
    title = ""
    if soup.find("title"):
        title = soup.find("title").get_text(strip=True)
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # 불필요 태그 제거
    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    # 본문 추출: article > main > body 순서로 시도
    body = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"(content|post|article|entry)", re.I))
        or soup.body
    )

    raw = (body or soup).get_text(separator="\n", strip=True)

    # 빈 줄 정리
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # 너무 길면 앞 6000자만 사용 (Claude 컨텍스트 절약)
    return BlogContent(title=title, text=cleaned[:6000], url=url)
