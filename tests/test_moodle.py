"""Moodle クライアントの純粋ロジックのテスト (ネットワーク非依存)."""

import asyncio
import base64
from datetime import datetime
from pathlib import Path

import pytest

from science_tokyo_lms_mcp.auth.token import TokenError, decode_launch_token
from science_tokyo_lms_mcp.client.moodle_client import (
    MoodleAPIError,
    MoodleClient,
    _strip_html,
    _to_datetime,
    append_token,
    flatten_params,
    safe_filename,
    same_host,
)
from science_tokyo_lms_mcp.config import Settings
from science_tokyo_lms_mcp.models import Material, MaterialKind


def test_flatten_params_nested() -> None:
    flat = flatten_params({"courseids": [10, 20], "options": {"flag": True}})
    assert flat == {
        "courseids[0]": "10",
        "courseids[1]": "20",
        "options[flag]": "1",
    }


def test_flatten_params_skips_none() -> None:
    assert flatten_params({"a": None, "b": 1}) == {"b": "1"}


def test_append_token_without_query() -> None:
    assert append_token("https://x/file.pdf", "T") == "https://x/file.pdf?token=T"


def test_append_token_with_query() -> None:
    assert append_token("https://x/f?forcedownload=1", "T") == "https://x/f?forcedownload=1&token=T"


def test_decode_launch_token_three_parts() -> None:
    payload = base64.b64encode(b"signature:::abc123:::private").decode()
    assert decode_launch_token(f"moodlemobile://token={payload}") == "abc123"


def test_decode_launch_token_single_part() -> None:
    payload = base64.b64encode(b"justtoken").decode()
    assert decode_launch_token(f"moodlemobile://token={payload}") == "justtoken"


def test_decode_launch_token_missing() -> None:
    with pytest.raises(TokenError):
        decode_launch_token("moodlemobile://nope")


def test_to_datetime_zero_is_none() -> None:
    assert _to_datetime(0) is None
    assert _to_datetime(None) is None


def test_to_datetime_converts() -> None:
    result = _to_datetime(1_700_000_000)
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_strip_html() -> None:
    assert _strip_html("<p>休講 <b>です</b></p>") == "休講 です"


def test_materials_from_file_module() -> None:
    client = MoodleClient(token="dummy")
    module = {
        "id": 42,
        "name": "第1回資料",
        "modname": "resource",
        "contents": [
            {"type": "file", "filename": "slide.pdf", "fileurl": "https://x/slide.pdf"},
        ],
    }
    materials = client._materials_from_module("100", module)
    assert len(materials) == 1
    assert materials[0].id == "42-0"
    assert materials[0].kind is MaterialKind.FILE
    assert materials[0].filename == "slide.pdf"


def test_materials_skips_contentless_module() -> None:
    client = MoodleClient(token="dummy")
    module = {"id": 9, "name": "見出し", "modname": "label"}
    assert client._materials_from_module("100", module) == []


def test_materials_from_url_module() -> None:
    client = MoodleClient(token="dummy")
    module = {"id": 7, "name": "参考リンク", "modname": "url", "url": "https://example.com"}
    materials = client._materials_from_module("100", module)
    assert len(materials) == 1
    assert materials[0].id == "7"
    assert materials[0].kind is MaterialKind.URL
    assert materials[0].url == "https://example.com"


def test_same_host_matches() -> None:
    assert same_host("https://lms.example/2025/x.pdf?token=T", "https://lms.example/2025/") is True


def test_same_host_rejects_other_host() -> None:
    assert same_host("https://evil.example/x.pdf", "https://lms.example/2025/") is False


def test_same_host_rejects_scheme_downgrade() -> None:
    assert same_host("http://lms.example/x.pdf", "https://lms.example/2025/") is False


def test_safe_filename_strips_path_traversal() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("/etc/shadow") == "shadow"
    assert safe_filename("a\\b\\c.pdf") == "c.pdf"


def test_safe_filename_keeps_plain_name() -> None:
    assert safe_filename("第1回資料.pdf") == "第1回資料.pdf"


def test_safe_filename_falls_back_when_empty() -> None:
    assert safe_filename("..") == "download"
    assert safe_filename("/") == "download"


def _file_settings() -> Settings:
    return Settings(token_backend="file", lms_base_url="https://lms.example/2025/")


def test_download_rejects_non_file_kind(tmp_path: Path) -> None:
    client = MoodleClient(settings=_file_settings(), token="dummy")
    material = Material(
        id="1",
        course_id="c",
        title="参考リンク",
        kind=MaterialKind.URL,
        url="https://lms.example/2025/page",
    )
    with pytest.raises(MoodleAPIError):
        asyncio.run(client.download_material(material, tmp_path))


def test_download_rejects_external_host(tmp_path: Path) -> None:
    client = MoodleClient(settings=_file_settings(), token="dummy")
    material = Material(
        id="1",
        course_id="c",
        title="外部ファイル",
        kind=MaterialKind.FILE,
        filename="x.pdf",
        url="https://evil.example/x.pdf",
    )
    with pytest.raises(MoodleAPIError):
        asyncio.run(client.download_material(material, tmp_path))
