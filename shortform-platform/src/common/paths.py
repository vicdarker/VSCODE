"""
경로·환경 추상화. Docker(Linux)와 로컬(Windows) 모두 작동.
환경변수로 오버라이드 가능.
"""

import os
import platform
import shutil
from pathlib import Path


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def is_linux() -> bool:
    return platform.system().lower().startswith("linux")


def is_in_docker() -> bool:
    """Docker 컨테이너 내부 실행 여부 추정."""
    if Path("/.dockerenv").exists():
        return True
    try:
        with open("/proc/1/cgroup") as f:
            return "docker" in f.read() or "containerd" in f.read()
    except Exception:
        return False


# ── Remotion ──
def remotion_dir() -> Path:
    """Remotion 프로젝트 루트. Docker 기본 /app/remotion, 로컬은 ./remotion."""
    env = os.environ.get("REMOTION_DIR")
    if env:
        return Path(env)
    if is_in_docker():
        return Path("/app/remotion")
    # 로컬: 프로젝트 루트 기준
    here = Path(__file__).resolve().parents[2]
    return here / "remotion"


# ── 폰트 ──
_FONT_CANDIDATES = {
    "noto_sans_kr_bold": [
        "/opt/korean-fonts/PretendardVariable.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        # Windows
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        # macOS
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ],
    "noto_emoji": [
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "C:/Windows/Fonts/seguiemj.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
    ],
    "korean_fonts_dir": [
        "/opt/korean-fonts",
    ],
}


def find_font(kind: str) -> str | None:
    """첫 번째 존재하는 폰트 경로 반환. None이면 로드 실패 → PIL default 폴백."""
    env_key = f"FONT_{kind.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    for p in _FONT_CANDIDATES.get(kind, []):
        if os.path.exists(p):
            return p
    return None


def korean_fonts_dir() -> Path:
    """한국 폰트 디렉토리. 없으면 빈 폴더 경로 (find_font_in_dir이 fallback 처리)."""
    p = find_font("korean_fonts_dir")
    return Path(p) if p else Path("/opt/korean-fonts")


# ── ffmpeg / ffprobe 자동 검출 (winget 등 비표준 경로 포함) ──
def ensure_ffmpeg_in_path() -> None:
    """ffmpeg가 PATH에 없으면 알려진 경로 추가."""
    if shutil.which("ffmpeg"):
        return
    candidates = [
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
            / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "ffmpeg-8.1-full_build/bin",
        Path("C:/ffmpeg/bin"),
        Path("/usr/local/bin"),
    ]
    for c in candidates:
        if (c / "ffmpeg.exe").exists() or (c / "ffmpeg").exists():
            os.environ["PATH"] = str(c) + os.pathsep + os.environ.get("PATH", "")
            return
