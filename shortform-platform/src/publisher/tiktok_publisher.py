"""
TikTok 자동 업로드 모듈
TikTok Content Posting API v2 사용

사전 준비:
  1. TikTok Developer Portal → 앱 생성
  2. "Content Posting API" 권한 신청 (심사 필요)
  3. 환경변수에 TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET 설정
  4. OAuth2 인증 후 access_token 발급

참고: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

import os
import json
import time
from pathlib import Path
from dataclasses import dataclass

import requests


TOKEN_PATH = "temp/tiktok_token.json"

TIKTOK_AUTH_URL   = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL  = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
TIKTOK_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


@dataclass
class UploadResult:
    platform: str
    video_id: str
    url: str


# ── 인증 ─────────────────────────────────────────────────────────────────

def get_auth_url(redirect_uri: str) -> str:
    """TikTok OAuth2 인증 URL을 생성합니다."""
    client_key = _require_env("TIKTOK_CLIENT_KEY")
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": "video.publish,video.upload",
        "redirect_uri": redirect_uri,
        "state": "shortform_platform",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{TIKTOK_AUTH_URL}?{query}"


def exchange_code(code: str, redirect_uri: str) -> dict:
    """인증 코드를 액세스 토큰으로 교환하고 저장합니다."""
    data = {
        "client_key":    _require_env("TIKTOK_CLIENT_KEY"),
        "client_secret": _require_env("TIKTOK_CLIENT_SECRET"),
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  redirect_uri,
    }
    resp = requests.post(TIKTOK_TOKEN_URL, data=data)
    resp.raise_for_status()
    token = resp.json()
    token["expires_at"] = time.time() + token.get("expires_in", 86400)
    _save_token(token)
    return token


def is_authenticated() -> bool:
    """저장된 TikTok 토큰이 유효한지 확인합니다."""
    token = _load_token()
    if not token:
        return False
    return time.time() < token.get("expires_at", 0)


# ── 업로드 ────────────────────────────────────────────────────────────────

def upload(
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
) -> UploadResult:
    """
    TikTok에 영상을 업로드합니다. (FILE_UPLOAD 방식)

    Args:
        video_path:  업로드할 .mp4 경로
        title:       영상 제목 (캡션)
        description: 추가 설명
        tags:        해시태그 목록 (['#tag1', '#tag2'])

    Returns:
        UploadResult (publish_id, url)
    """
    token = _load_token()
    if not token or not is_authenticated():
        raise RuntimeError("TikTok 인증이 필요합니다. /api/publish/tiktok/auth 를 먼저 방문하세요.")

    access_token = token["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    file_size = Path(video_path).stat().st_size

    # Step 1: 업로드 초기화
    caption = _build_caption(title, tags)
    init_body = {
        "post_info": {
            "title": caption[:2200],
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,   # 단일 청크
            "total_chunk_count": 1,
        },
    }

    init_resp = requests.post(TIKTOK_UPLOAD_URL, headers=headers, json=init_body)
    init_resp.raise_for_status()
    init_data = init_resp.json()["data"]

    publish_id  = init_data["publish_id"]
    upload_url  = init_data["upload_url"]

    # Step 2: 파일 업로드
    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_headers = {
        "Content-Type": "video/mp4",
        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        "Content-Length": str(file_size),
    }
    up_resp = requests.put(upload_url, headers=upload_headers, data=video_data)
    up_resp.raise_for_status()

    # Step 3: 처리 완료 대기 (최대 60초 폴링)
    _wait_for_processing(publish_id, access_token)

    return UploadResult(
        platform="tiktok",
        video_id=publish_id,
        url=f"https://www.tiktok.com/@me/video/{publish_id}",
    )


def _wait_for_processing(publish_id: str, access_token: str, timeout: int = 60):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.post(
            TIKTOK_STATUS_URL,
            headers=headers,
            json={"publish_id": publish_id},
        )
        if resp.ok:
            status = resp.json().get("data", {}).get("status", "")
            if status == "PUBLISH_COMPLETE":
                return
            if status in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"TikTok 업로드 실패: {status}")
        time.sleep(3)


def _build_caption(title: str, tags: list[str] | None) -> str:
    caption = title
    if tags:
        tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in tags)
        caption = f"{title}\n\n{tag_str}"
    return caption


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────

def _require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise RuntimeError(f"환경변수 {key} 가 설정되지 않았습니다.")
    return val


def _save_token(token: dict):
    Path(TOKEN_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(TOKEN_PATH).write_text(json.dumps(token), encoding="utf-8")


def _load_token() -> dict | None:
    if not Path(TOKEN_PATH).exists():
        return None
    return json.loads(Path(TOKEN_PATH).read_text(encoding="utf-8"))
