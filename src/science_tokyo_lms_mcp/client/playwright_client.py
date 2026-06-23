"""ブラウザ巡回による LMS クライアント (基盤非依存).

:class:`~science_tokyo_lms_mcp.auth.session.BrowserSession` の認証済み
セッションを用いて LMS のページを巡回し，必要な情報を抽出する実装．

現時点では LMS の基盤が未特定のため，各メソッドは未実装である．
基盤特定後 (Moodle なら API クライアントへの差し替えも検討) に，
ページ解析ロジックをここへ実装する．
"""

from __future__ import annotations

from pathlib import Path

from science_tokyo_lms_mcp.auth.session import BrowserSession
from science_tokyo_lms_mcp.config import Settings, get_settings
from science_tokyo_lms_mcp.models import Announcement, Assignment, Course, Material

_NOT_IMPLEMENTED_MSG = (
    "LMS 基盤が未特定のため未実装です．"
    "ログイン後の LMS の URL とページ構造を特定し，"
    "client/playwright_client.py に解析ロジックを実装してください．"
)


class PlaywrightLMSClient:
    """Playwright を用いた LMS クライアント (スタブ).

    :class:`~science_tokyo_lms_mcp.client.base.LMSClient` プロトコルに適合する．
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """クライアントを初期化する.

        Args:
            settings: 実行時設定．省略時は :func:`get_settings` を用いる．
        """
        self.settings = settings or get_settings()
        self.session = BrowserSession(self.settings)

    async def list_courses(self) -> list[Course]:
        """履修中コースの一覧を取得する (未実装)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def list_materials(self, course_id: str) -> list[Material]:
        """指定コースの講義資料一覧を取得する (未実装)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def download_material(self, material: Material, dest_dir: Path) -> Path:
        """講義資料をダウンロードする (未実装)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def list_assignments(self, course_id: str | None = None) -> list[Assignment]:
        """課題と締切の一覧を取得する (未実装)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def list_announcements(self, course_id: str | None = None) -> list[Announcement]:
        """お知らせ・休講情報の一覧を取得する (未実装)."""
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
