"""
YouTube Shorts 자동 업로드 모듈
Google OAuth2 → YouTube Data API v3 사용

사전 준비:
  1. Google Cloud Console → YouTube Data API v3 활성화
  2. OAuth 2.0 클라이언트 ID (데스크톱 앱) 생성 → client_secrets.json 저장
  3. 환경변수 YOUTUBE_CLIENT_SECRETS_PATH 에 경로 지정
"""

import os
import json
import pickle
from pathlib import Path
from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = "temp/youtube_token.pkl"


@dataclass
class UploadResult:
    platform: str
    video_id: str
    url: str


# ── 인증 ─────────────────────────────────────────────────────────────────

def get_auth_url(redirect_uri: str) -> str:
    """OAuth2 인증 URL을 생성합니다. 브라우저에서 열어 사용자 승인을 받습니다."""
    flow = _make_flow(redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def exchange_code(code: str, redirect_uri: str) -> Credentials:
    """인증 코드를 액세스 토큰으로 교환하고 로컬에 저장합니다."""
    flow = _make_flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_token(creds)
    return creds


def is_authenticated() -> bool:
    """저장된 YouTube 토큰이 유효한지 확인합니다."""
    creds = _load_token()
    if not creds:
        return False
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return True
        except Exception:
            return False
    return creds.valid


# ── 업로드 ────────────────────────────────────────────────────────────────

def upload(
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    thumbnail_path: str | None = None,
    made_for_kids: bool = False,
) -> UploadResult:
    """
    YouTube Shorts로 영상을 업로드합니다.

    Args:
        video_path:      업로드할 .mp4 경로
        title:           영상 제목 (최대 100자)
        description:     영상 설명
        tags:            태그 목록
        thumbnail_path:  썸네일 경로 (None이면 자동 선택)
        made_for_kids:   아동용 여부

    Returns:
        UploadResult (video_id, url)
    """
    creds = _load_token()
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_token(creds)
        else:
            raise RuntimeError("YouTube 인증이 필요합니다. /api/publish/youtube/auth 를 먼저 방문하세요.")

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": tags or [],
            "categoryId": "22",        # People & Blogs
            "defaultLanguage": "ko",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=4 * 1024 * 1024,  # 4 MB 청크
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]

    # 썸네일 업로드 (채널 인증이 있는 경우만 가능)
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
            ).execute()
        except Exception:
            pass  # 썸네일 업로드 실패는 무시

    return UploadResult(
        platform="youtube",
        video_id=video_id,
        url=f"https://www.youtube.com/shorts/{video_id}",
    )


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────

def _make_flow(redirect_uri: str) -> Flow:
    secrets_path = os.environ.get("YOUTUBE_CLIENT_SECRETS_PATH", "client_secrets.json")
    return Flow.from_client_secrets_file(
        secrets_path,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def _save_token(creds: Credentials):
    Path(TOKEN_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)


def _load_token() -> Credentials | None:
    if not Path(TOKEN_PATH).exists():
        return None
    with open(TOKEN_PATH, "rb") as f:
        return pickle.load(f)
