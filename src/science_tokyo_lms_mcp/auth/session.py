"""Playwright 永続セッションの管理.

SSO ログイン (MFA 含む) は初回のみ手動で行う前提とし，認証済みの状態を
永続プロファイル (``user_data_dir``) に保存して再利用する．主にモバイル
トークン取得フロー (:mod:`science_tokyo_lms_mcp.auth.token`) から用いる．
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.async_api import async_playwright

from science_tokyo_lms_mcp.config import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from playwright.async_api import BrowserContext


class BrowserSession:
    """永続プロファイルを用いたブラウザセッション.

    Attributes:
        settings: 実行時設定．
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """セッションを初期化する.

        Args:
            settings: 実行時設定．省略時は :func:`get_settings` を用いる．
        """
        self.settings = settings or get_settings()

    @asynccontextmanager
    async def context(self, *, headless: bool | None = None) -> AsyncIterator[BrowserContext]:
        """永続プロファイルでブラウザコンテキストを開く.

        Args:
            headless: ヘッドレス実行の上書き指定．省略時は設定値に従う．

        Yields:
            認証状態を保持した :class:`BrowserContext`．
        """
        user_data_dir = Path(self.settings.user_data_dir).expanduser()
        user_data_dir.mkdir(parents=True, exist_ok=True)
        is_headless = self.settings.headless if headless is None else headless

        async with async_playwright() as pw:
            launchers = {"chromium": pw.chromium, "firefox": pw.firefox, "webkit": pw.webkit}
            ctx = await launchers[self.settings.browser].launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=is_headless,
            )
            ctx.set_default_navigation_timeout(self.settings.nav_timeout_ms)
            try:
                yield ctx
            finally:
                await ctx.close()
