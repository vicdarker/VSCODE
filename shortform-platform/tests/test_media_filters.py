"""media_searcher 핵심 헬퍼 단위 테스트."""
import pytest


def test_small_image_url_filter():
    from src.searcher.media_searcher import _is_small_image_url
    assert _is_small_image_url("https://x.com/img/90x67/foo.jpg")
    assert _is_small_image_url("https://x.com/mnews90x67/foo.jpg")
    assert _is_small_image_url("https://x.com/img/photo-150x100.jpg")
    assert _is_small_image_url("https://x.com/photo_thumb.jpg")
    assert _is_small_image_url("https://x.com/photo_s.jpg")
    assert _is_small_image_url("https://x.com/img/thumb/foo.jpg")
    # 본문 사진은 통과
    assert not _is_small_image_url("https://x.com/article/big-news.jpg")
    assert not _is_small_image_url("https://x.com/view610/foo.jpg")


def test_img_width_attr():
    from src.searcher.media_searcher import _img_width_attr
    assert _img_width_attr('src="x" width="100"') == 100
    assert _img_width_attr("width=400 src='x'") == 400
    assert _img_width_attr("alt='no width'") is None


def test_looks_like_person_page():
    from src.searcher.media_searcher import _looks_like_person_page
    # 인물 페이지 패턴
    assert _looks_like_person_page("이장우", "이장우")
    assert _looks_like_person_page("이장우 (1965년)", "이장우")
    assert _looks_like_person_page("박지원 (정치인)", "박지원")
    # 사건/선거 페이지는 거부
    assert not _looks_like_person_page("이재명 대통령 취임식", "이재명")
    assert not _looks_like_person_page("2021년 도널드 트럼프 탄핵", "트럼프")


def test_extract_title_keyword():
    from src.searcher.media_searcher import _extract_title_keyword
    assert _extract_title_keyword("이장우 대전시장 개혁 발표", "이장우") == "시장"
    assert _extract_title_keyword("박지원 의원 비판 발언", "박지원") == "의원"
    # subject 자체에서 추출 안 함 (자기 이름 제외)
    assert _extract_title_keyword("이재명 대통령 행사", "이재명") == "대통령"
    # 없으면 빈 문자열
    assert _extract_title_keyword("일반 뉴스", "주제") == ""


def test_article_image_pool_fifo():
    from src.searcher.media_searcher import ArticleImagePool
    pool = ArticleImagePool(["a", "b", "c"])
    assert pool.remaining() == 3
    assert pool.take() == "a"
    assert pool.take() == "b"
    assert pool.remaining() == 1
    assert pool.take() == "c"
    assert pool.take() is None
    assert pool.remaining() == 0
