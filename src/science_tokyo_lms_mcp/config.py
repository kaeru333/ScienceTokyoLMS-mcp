"""MCP サーバの設定.

環境変数 (接頭辞 ``STLMS_``) または ``.env`` から設定を読み込む．
パスワード等の機密情報そのものは扱わず，SSO ログインは Playwright の
永続プロファイルに，Web Services トークンは keyring (または .auth 配下の
ファイル) に保管する方針とする．
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """MCP サーバの実行時設定."""

    model_config = SettingsConfigDict(
        env_prefix="STLMS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    portal_url: str = Field(
        default="https://portal.isct.ac.jp/",
        description="Science Tokyo ポータルの URL.",
    )
    lms_base_url: str = Field(
        default="https://lms.s.isct.ac.jp/2025/",
        description="Moodle (Science Tokyo LMS) のベース URL．年度ごとにパスが分かれる.",
    )
    service: str = Field(
        default="moodle_mobile_app",
        description="トークン発行に用いる Moodle Web Service 名.",
    )
    url_scheme: str = Field(
        default="moodlemobile",
        description="モバイルトークン取得フローで用いる URL スキーム.",
    )
    browser: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium",
        description="トークン取得に用いるブラウザエンジン (chromium / firefox / webkit).",
    )
    keyring_service: str = Field(
        default="science-tokyo-lms-mcp",
        description="keyring に保存する際のサービス名.",
    )
    token_backend: Literal["auto", "keyring", "file"] = Field(
        default="auto",
        description="トークンの保存方式．keyring が使えない場合は file を指定する.",
    )
    wstoken: str | None = Field(
        default=None,
        description="トークンを直接指定する場合の値 (.env 等で設定．最優先).",
    )
    token_file: Path = Field(
        default=Path(".auth/wstoken"),
        description="keyring が使えない環境でのトークン保存先 (.gitignore 済み).",
    )
    user_data_dir: Path = Field(
        default=Path(".auth/profile"),
        description="Playwright 永続プロファイルの保存先 (cookie・セッション保持).",
    )
    download_dir: Path = Field(
        default=Path("downloads"),
        description="講義資料のダウンロード先ディレクトリ.",
    )
    headless: bool = Field(
        default=False,
        description="ヘッドレス実行するか．初回トークン取得時は false 推奨.",
    )
    nav_timeout_ms: int = Field(
        default=30_000,
        description="ページ遷移のタイムアウト (ミリ秒).",
    )
    http_timeout_s: float = Field(
        default=60.0,
        description="Web Services / ファイル取得の HTTP タイムアウト (秒).",
    )
    auto_relogin: bool = Field(
        default=True,
        description="トークン無効検知時にヘッドレスで自動再ログインするか．false で即エラー.",
    )
    relogin_timeout_s: float = Field(
        default=45.0,
        description="ヘッドレス再ログインでトークン取得を待つ上限秒．超えたら MFA 必要とみなす.",
    )
    relogin_cooldown_s: float = Field(
        default=60.0,
        description="ヘッドレス再ログイン失敗後，再試行を抑止する秒数 (ブラウザ多重起動の防止).",
    )
    login_timeout_s: int = Field(
        default=300,
        description="手動 (GUI) ログインでトークン取得を待つ上限秒．MFA 入力の猶予.",
    )

    @property
    def ws_endpoint(self) -> str:
        """Web Services REST エンドポイントの URL を返す."""
        return f"{self.lms_base_url.rstrip('/')}/webservice/rest/server.php"

    @property
    def launch_url(self) -> str:
        """モバイルトークン取得用 launch.php の URL を返す."""
        base = self.lms_base_url.rstrip("/")
        return f"{base}/admin/tool/mobile/launch.php"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定インスタンスを取得する (プロセス内でキャッシュ).

    Returns:
        読み込み済みの :class:`Settings` インスタンス．
    """
    return Settings()
