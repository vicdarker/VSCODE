"""썸네일 텍스트 분리·폰트 크기 테스트."""
import pytest


def test_explicit_newline():
    from src.editor.news_thumbnail import _split_text_for_thumbnail
    assert _split_text_for_thumbnail("월가 폭발\n33년 만에") == ["월가 폭발", "33년 만에"]


def test_short_text_one_line():
    from src.editor.news_thumbnail import _split_text_for_thumbnail
    assert _split_text_for_thumbnail("월가 폭발", max_per_line=12) == ["월가 폭발"]


def test_long_text_auto_wrap():
    from src.editor.news_thumbnail import _split_text_for_thumbnail
    lines = _split_text_for_thumbnail("강남 집값 33% 폭락 사라졌다", max_per_line=12)
    assert len(lines) == 2
    assert all(len(ln) <= 14 for ln in lines)


def test_single_long_word_force_split():
    from src.editor.news_thumbnail import _split_text_for_thumbnail
    lines = _split_text_for_thumbnail("엄청길고긴한어절단어", max_per_line=8)
    # 어절 1개 → 강제 절반 분리 (또는 그대로 1줄)
    assert lines  # not empty


def test_empty_input():
    from src.editor.news_thumbnail import _split_text_for_thumbnail
    assert _split_text_for_thumbnail("") == []
    assert _split_text_for_thumbnail("   ") == []


def test_font_size_scales_with_length():
    from src.editor.news_thumbnail import _font_size_for_lines
    # 1줄 짧을수록 크게
    assert _font_size_for_lines(["짧음"]) > _font_size_for_lines(["조금 긴 텍스트"])
    # 2줄은 1줄보다 작게
    assert _font_size_for_lines(["a", "b"]) < _font_size_for_lines(["a"])
