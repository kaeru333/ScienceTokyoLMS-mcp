"""お知らせ・休講情報関連の MCP ツール."""

from __future__ import annotations

from typing import TYPE_CHECKING

from science_tokyo_lms_mcp.client import get_client
from science_tokyo_lms_mcp.models import Announcement

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """お知らせ関連ツールを登録する.

    Args:
        mcp: 登録先の FastMCP インスタンス．
    """

    @mcp.tool()
    async def list_announcements(course_id: str | None = None) -> list[Announcement]:
        """お知らせ・休講情報の一覧を取得する.

        Args:
            course_id: コースの識別子．省略時は全コース横断．

        Returns:
            お知らせの一覧．
        """
        return await get_client().list_announcements(course_id)
