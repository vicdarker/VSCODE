"""worker._friendly_error 매핑 테스트."""
import json
import pytest


@pytest.fixture
def fr():
    from worker.tasks import _friendly_error
    return _friendly_error


def test_anthropic_key_missing(fr):
    msg = fr(KeyError("ANTHROPIC_API_KEY"))
    assert "Claude API 키" in msg
    assert "ANTHROPIC_API_KEY" in msg


def test_openai_key_missing(fr):
    msg = fr(RuntimeError("OPENAI_API_KEY 환경변수 없음"))
    assert "OpenAI API 키" in msg


def test_json_parse_error(fr):
    err = json.JSONDecodeError("Expecting value", "x", 0)
    msg = fr(err)
    assert "Claude 응답 파싱" in msg


def test_timeout(fr):
    msg = fr(TimeoutError("request timed out"))
    assert "응답 지연" in msg


def test_unknown_falls_back_to_first_line(fr):
    err = RuntimeError("뭔가 이상한 에러\n2번째 줄")
    msg = fr(err)
    assert msg.startswith("RuntimeError:")
    assert "뭔가 이상한 에러" in msg
    assert "2번째 줄" not in msg


def test_korean_passthrough(fr):
    msg = fr(ValueError("뉴스 내용을 가져올 수 없습니다."))
    assert msg == "뉴스 내용을 가져올 수 없습니다."
