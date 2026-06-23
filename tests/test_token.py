"""トークン保存・読込ロジックのテスト (keyring 非依存)."""

from pathlib import Path

from science_tokyo_lms_mcp.auth.token import load_token, save_token
from science_tokyo_lms_mcp.config import Settings


def test_wstoken_takes_priority() -> None:
    settings = Settings(wstoken="DIRECT", token_backend="file")
    assert load_token(settings) == "DIRECT"


def test_file_backend_roundtrip(tmp_path: Path) -> None:
    token_file = tmp_path / "wstoken"
    settings = Settings(token_backend="file", token_file=token_file)
    save_token("ABC123", settings)
    assert token_file.read_text(encoding="utf-8") == "ABC123"
    assert load_token(settings) == "ABC123"


def test_file_backend_returns_none_when_absent(tmp_path: Path) -> None:
    settings = Settings(token_backend="file", token_file=tmp_path / "missing")
    assert load_token(settings) is None
