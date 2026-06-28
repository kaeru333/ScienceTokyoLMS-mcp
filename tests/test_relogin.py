"""トークン切れ時の自動再ログイン挙動のテスト (ネットワーク非依存).

フェイクの ``httpx.AsyncClient`` と ``acquire_token`` / ``save_token`` を
monkeypatch で差し込み，認証エラー検知・自動リトライ・並行集約・クールダウン・
抑止条件を検証する．HTTP 応答は本物の :class:`httpx.Response` を用いる．
"""

import asyncio

import httpx
import pytest

from science_tokyo_lms_mcp.auth.token import ReauthRequiredError
from science_tokyo_lms_mcp.client import moodle_client
from science_tokyo_lms_mcp.client.moodle_client import (
    AuthRequiredError,
    MoodleClient,
    TokenExpiredError,
    _is_auth_errorcode,
    _is_auth_status,
)
from science_tokyo_lms_mcp.config import Settings
from science_tokyo_lms_mcp.models import Material, MaterialKind


def _resp(*, json_data=None, status=200, content=None):
    """本物の httpx.Response を組み立てて返す."""
    request = httpx.Request("GET", "http://test")
    if content is not None:
        return httpx.Response(status_code=status, content=content, request=request)
    if json_data is not None:
        return httpx.Response(status_code=status, json=json_data, request=request)
    return httpx.Response(status_code=status, request=request)


def _invalid_payload():
    """Moodle がトークン無効時に返す REST 応答 (HTTP 200) を模す."""
    return {
        "exception": "moodle_exception",
        "errorcode": "invalidtoken",
        "message": "Invalid token",
    }


def _make_async_client(*, post_fn=None, get_fn=None):
    """post_fn / get_fn に処理を委譲するフェイク AsyncClient クラスを返す."""

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None, **kwargs):
            assert post_fn is not None
            return post_fn(url, data)

        async def get(self, url, **kwargs):
            assert get_fn is not None
            return get_fn(url)

    return _Client


def _make_fake_acquire(*, result=None, exc=None):
    """呼び出し回数を数えるフェイク acquire_token と状態 dict を返す."""
    state = {"calls": 0}

    async def _fake(settings=None, *, headless=None):
        state["calls"] += 1
        if exc is not None:
            raise exc
        return result

    return _fake, state


def _patch(monkeypatch, *, client_cls, acquire):
    """httpx.AsyncClient / acquire_token / save_token を差し替える."""
    monkeypatch.setattr(moodle_client.httpx, "AsyncClient", client_cls)
    monkeypatch.setattr(moodle_client, "acquire_token", acquire)
    monkeypatch.setattr(moodle_client, "save_token", lambda *a, **k: None)


# --- 純粋関数 ---------------------------------------------------------------


def test_is_auth_errorcode():
    assert _is_auth_errorcode("invalidtoken") is True
    assert _is_auth_errorcode("accesstokeninvalid") is True
    assert _is_auth_errorcode("tokenexpired") is True
    assert _is_auth_errorcode("accessexception") is False
    assert _is_auth_errorcode(None) is False


def test_is_auth_status():
    assert _is_auth_status(401) is True
    assert _is_auth_status(403) is True
    assert _is_auth_status(200) is False
    assert _is_auth_status(500) is False


# --- 自動リトライ -----------------------------------------------------------


def test_call_relogin_then_success(monkeypatch):
    """1 回目 invalidtoken → 自動再ログイン → 2 回目成功で結果が返る."""
    calls = {"post": 0}

    def post_fn(url, data):
        calls["post"] += 1
        if data.get("wstoken") == "new-token":
            return _resp(json_data={"userid": 7})
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(result="new-token")
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(settings=Settings(token_backend="file"), token="old-token")

    result = asyncio.run(client._call("core_webservice_get_site_info"))

    assert result == {"userid": 7}
    assert acq["calls"] == 1
    assert client._token == "new-token"
    assert calls["post"] == 2


def test_call_retry_only_once(monkeypatch):
    """2 回目も invalidtoken なら TokenExpiredError を送出し，3 回目は呼ばない."""
    calls = {"post": 0}

    def post_fn(url, data):
        calls["post"] += 1
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(result="new-token")
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(settings=Settings(token_backend="file"), token="old-token")

    with pytest.raises(TokenExpiredError):
        asyncio.run(client._call("f"))

    assert acq["calls"] == 1
    assert calls["post"] == 2


def test_call_mfa_required_returns_guidance(monkeypatch):
    """ヘッドレス再取得が MFA 必要で失敗したら案内付き AuthRequiredError を返す."""
    calls = {"post": 0}

    def post_fn(url, data):
        calls["post"] += 1
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(
        exc=ReauthRequiredError(
            "自動再ログインに失敗しました．`uv run science-tokyo-lms-login` を実行してください．"
        )
    )
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(settings=Settings(token_backend="file"), token="old-token")

    with pytest.raises(AuthRequiredError) as ei:
        asyncio.run(client._call("f"))

    assert "science-tokyo-lms-login" in str(ei.value)
    assert acq["calls"] == 1
    assert calls["post"] == 1


def test_concurrent_relogin_aggregated(monkeypatch):
    """同時多発の認証エラーでも acquire_token はちょうど 1 回に集約される."""

    def post_fn(url, data):
        if data.get("wstoken") == "new-token":
            return _resp(json_data={"ok": True})
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(result="new-token")
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(settings=Settings(token_backend="file"), token="old-token")

    async def run_all():
        return await asyncio.gather(*[client._call("f") for _ in range(10)])

    results = asyncio.run(run_all())

    assert all(r == {"ok": True} for r in results)
    assert acq["calls"] == 1


def test_cooldown_skips_browser_on_repeated_failure(monkeypatch):
    """MFA 必要で失敗した直後はクールダウン中でブラウザを再起動しない."""

    def post_fn(url, data):
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(exc=ReauthRequiredError("login"))
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(
        settings=Settings(token_backend="file", relogin_cooldown_s=60.0),
        token="old-token",
    )

    with pytest.raises(AuthRequiredError):
        asyncio.run(client._call("f"))
    assert acq["calls"] == 1

    with pytest.raises(AuthRequiredError):
        asyncio.run(client._call("f"))
    assert acq["calls"] == 1  # クールダウン中なので acquire_token は呼ばれない


def test_no_relogin_when_auto_disabled(monkeypatch):
    """auto_relogin=False なら再ログインせず即 AuthRequiredError."""

    def post_fn(url, data):
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(result="new-token")
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(settings=Settings(token_backend="file", auto_relogin=False), token="old")

    with pytest.raises(AuthRequiredError):
        asyncio.run(client._call("f"))
    assert acq["calls"] == 0


def test_no_relogin_when_wstoken_set(monkeypatch):
    """wstoken 明示時は load_token で上書きできないため再ログインを抑止する."""

    def post_fn(url, data):
        return _resp(json_data=_invalid_payload())

    acquire, acq = _make_fake_acquire(result="new-token")
    _patch(monkeypatch, client_cls=_make_async_client(post_fn=post_fn), acquire=acquire)
    client = MoodleClient(settings=Settings(token_backend="file", wstoken="WS"), token="WS")

    with pytest.raises(AuthRequiredError):
        asyncio.run(client._call("f"))
    assert acq["calls"] == 0


def test_download_auto_relogin(monkeypatch, tmp_path):
    """ファイル DL が 401 を返したら自動再ログインして新トークンでリトライする."""

    def get_fn(url):
        if "token=new-token" in url:
            return _resp(status=200, content=b"PDFDATA")
        return _resp(status=401, content=b"")

    acquire, acq = _make_fake_acquire(result="new-token")
    _patch(monkeypatch, client_cls=_make_async_client(get_fn=get_fn), acquire=acquire)
    settings = Settings(token_backend="file", lms_base_url="https://lms.example/2025/")
    client = MoodleClient(settings=settings, token="old-token")
    material = Material(
        id="1",
        course_id="c",
        title="資料",
        kind=MaterialKind.FILE,
        filename="x.pdf",
        url="https://lms.example/2025/x.pdf",
    )

    dest = asyncio.run(client.download_material(material, tmp_path))

    assert dest.read_bytes() == b"PDFDATA"
    assert acq["calls"] == 1


# --- User-Agent 付与 (LMS 前段 ELB の 403 対策) ------------------------------


def test_default_user_agent_is_browser_like():
    """既定 user_agent はブラウザ風で，python-httpx を含まない."""
    ua = Settings(token_backend="file").user_agent
    assert ua
    assert "python-httpx" not in ua
    assert ua.startswith("Mozilla/")


def test_call_sends_browser_user_agent(monkeypatch):
    """WS 呼び出し時の httpx クライアントにブラウザ風 User-Agent が設定される.

    既定の python-httpx UA は LMS 前段の AWS ELB に 403 で弾かれるため，
    クライアント生成時に User-Agent を上書きしていることを検証する．
    """
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, *args, **kwargs):
            captured["headers"] = kwargs.get("headers")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, data=None, **kwargs):
            return _resp(json_data={"userid": 7})

    monkeypatch.setattr(moodle_client.httpx, "AsyncClient", _Client)
    client = MoodleClient(settings=Settings(token_backend="file"), token="tok")

    asyncio.run(client._call("core_webservice_get_site_info"))

    headers = captured["headers"]
    assert isinstance(headers, dict)
    ua = headers.get("User-Agent")
    assert isinstance(ua, str)
    assert not ua.startswith("python-httpx")
