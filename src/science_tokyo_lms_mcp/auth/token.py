"""Moodle モバイルトークンの取得と保管.

Science Tokyo の LMS は SAML2 SSO (MFA 必須) で保護されているため，
パスワードによるトークン発行 (``login/token.php``) は使えない．代わりに
モバイルアプリと同じ launch フロー (``admin/tool/mobile/launch.php``) を
ブラウザで実行し，SSO 完了後に返る ``<scheme>://token=...`` を捕捉する．
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
from pathlib import Path
from urllib.parse import unquote, urlsplit

import keyring
from keyring.errors import KeyringError

from science_tokyo_lms_mcp.auth.session import BrowserSession
from science_tokyo_lms_mcp.config import Settings, get_settings

logger = logging.getLogger(__name__)


class TokenError(RuntimeError):
    """トークンの取得・復号・保管に失敗した場合に送出する."""


class ReauthRequiredError(TokenError):
    """ヘッドレス再取得が SSO セッション切れ (MFA 必要) で失敗した場合に送出する.

    呼び出し側はこれを捕捉し，ユーザーに ``uv run science-tokyo-lms-login`` を
    案内する終端エラーへ変換する．
    """


def decode_launch_token(scheme_url: str) -> str:
    """モバイル launch フローのリダイレクト URL からトークンを復号する.

    Moodle は ``<scheme>://token=<base64>`` 形式で返す．base64 を復号すると
    ``<署名>:::<トークン>:::<秘密トークン>`` となるため，トークン部を取り出す．

    Args:
        scheme_url: ``<scheme>://token=...`` 形式の URL．

    Returns:
        Web Services トークン文字列．

    Raises:
        TokenError: URL からトークンを取り出せない場合．
    """
    if "token=" not in scheme_url:
        raise TokenError(f"トークンを含まない URL です: {scheme_url}")
    raw = unquote(scheme_url.split("token=", 1)[1].split("&", 1)[0])
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise TokenError(f"base64 復号に失敗しました: {exc}") from exc
    parts = decoded.split(":::")
    token = parts[1] if len(parts) >= 2 else parts[0]
    if not token:
        raise TokenError("トークンが空でした．")
    return token


def _write_token_file(settings: Settings, token: str) -> None:
    """トークンをファイル (パーミッション 0600) に保存する."""
    path = Path(settings.token_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)


def save_token(token: str, settings: Settings | None = None) -> None:
    """トークンを保存する (``token_backend`` 設定に従う).

    ``token_backend`` が ``file`` の場合は keyring を使わずファイルに保存する．
    ``auto`` / ``keyring`` の場合はまず keyring を試し，失敗時はファイルへ退避する．

    Args:
        token: 保存する Web Services トークン．
        settings: 実行時設定．省略時は :func:`get_settings` を用いる．
    """
    s = settings or get_settings()
    if s.token_backend != "file":
        try:
            keyring.set_password(s.keyring_service, s.lms_base_url, token)
            logger.info("トークンを keyring に保存しました．")
            return
        except KeyringError as exc:
            logger.warning("keyring へ保存できないためファイルに保存します: %s", exc)
    _write_token_file(s, token)
    logger.info("トークンをファイルに保存しました: %s", s.token_file)


def load_token(settings: Settings | None = None) -> str | None:
    """保存済みトークンを読み込む.

    ``wstoken`` が設定されていれば最優先で用いる．次に ``token_backend`` が
    ``file`` 以外なら keyring を，最後にファイルを参照する．

    Args:
        settings: 実行時設定．省略時は :func:`get_settings` を用いる．

    Returns:
        トークン文字列．未保存なら ``None``．
    """
    s = settings or get_settings()
    if s.wstoken:
        return s.wstoken
    if s.token_backend != "file":
        try:
            token = keyring.get_password(s.keyring_service, s.lms_base_url)
            if token:
                return token
        except KeyringError as exc:
            logger.warning("keyring から読み込めませんでした: %s", exc)
    path = Path(s.token_file).expanduser()
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def _needs_interactive_auth(url: str | None, settings: Settings) -> bool:
    """遷移先が「対話的認証 (MFA 等) が必要」であることを示すか判定する.

    有効な SSO セッションがあれば launch フローは LMS ホスト内で完結し，最後に
    custom scheme へ遷移する．LMS でも custom scheme でもない外部ホスト
    (Extic / SAML IdP 等) へ出た時点で対話的認証が必要と判断する．特定の IdP
    ドメインに依存しないため頑健である．

    Args:
        url: 遷移先 URL．
        settings: 実行時設定．

    Returns:
        外部ホストへ遷移しており対話的認証が必要なら ``True``．
    """
    if not url or url.startswith(f"{settings.url_scheme}://"):
        return False
    parts = urlsplit(url)
    if not parts.netloc:
        return False
    return parts.netloc != urlsplit(settings.lms_base_url).netloc


async def acquire_token(settings: Settings | None = None, *, headless: bool | None = None) -> str:
    """ブラウザの SSO ログインを経てトークンを取得する.

    永続プロファイルに SSO セッションが残っていれば，MFA の再入力なしで
    自動的に取得が完了することがある．``headless=True`` の場合は，外部 IdP への
    遷移 (MFA 必要) を検知した時点で早期に :class:`ReauthRequiredError` を送出する．

    Args:
        settings: 実行時設定．省略時は :func:`get_settings` を用いる．
        headless: ヘッドレス実行の上書き指定．省略時は ``settings.headless`` に従う．

    Returns:
        取得した Web Services トークン．

    Raises:
        ReauthRequiredError: ヘッドレスで SSO セッション切れ (MFA 必要) を検知した場合．
        TokenError: 時間内にトークンを取得できなかった場合．
    """
    s = settings or get_settings()
    is_headless = s.headless if headless is None else headless
    passport = random.randint(1, 1_000_000_000)
    launch_url = f"{s.launch_url}?service={s.service}&passport={passport}&urlscheme={s.url_scheme}"
    prefix = f"{s.url_scheme}://"
    captured: dict[str, str] = {}
    done = asyncio.Event()
    reauth = asyncio.Event()

    def remember(url: str | None) -> None:
        if url and url.startswith(prefix) and "url" not in captured:
            captured["url"] = url
            done.set()

    def watch_interactive(url: str | None) -> None:
        # ヘッドレス時のみ早期判定する．トークン捕捉後は無視する．
        if is_headless and not done.is_set() and _needs_interactive_auth(url, s):
            reauth.set()

    session = BrowserSession(s)
    async with session.context(headless=is_headless) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("request", lambda req: remember(req.url))
        page.on("response", lambda resp: remember(resp.headers.get("location")))
        page.on("framenavigated", lambda frame: watch_interactive(frame.url))
        if not is_headless:
            print("ブラウザで Science Tokyo の SSO ログイン (MFA 含む) を完了してください．")
        try:
            await page.goto(launch_url, wait_until="commit")
        except Exception as exc:  # ログイン済みだと custom scheme 遷移で例外になり得る
            logger.debug("launch 遷移時の例外 (想定内のことがある): %s", exc)

        timeout = s.relogin_timeout_s if is_headless else s.login_timeout_s
        done_task = asyncio.ensure_future(done.wait())
        reauth_task = asyncio.ensure_future(reauth.wait())
        try:
            await asyncio.wait(
                {done_task, reauth_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            done_task.cancel()
            reauth_task.cancel()

    if "url" not in captured:
        if is_headless:
            raise ReauthRequiredError(
                "自動再ログインに失敗しました (SSO セッション切れ・MFA が必要)．"
                "`uv run science-tokyo-lms-login` を実行してください．"
            )
        raise TokenError("時間内にトークンを取得できませんでした．")

    return decode_launch_token(captured["url"])
