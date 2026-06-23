"""コース関連の MCP ツール."""

from __future__ import annotations

from typing import TYPE_CHECKING

from science_tokyo_lms_mcp.client import get_client
from science_tokyo_lms_mcp.models import Course

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """コース関連ツールを登録する.

    Args:
        mcp: 登録先の FastMCP インスタンス．
    """

    @mcp.tool()
    async def list_courses() -> list[Course]:
        """履修中のコース一覧を取得する.

        Returns:
            コースの一覧．
        """
        return await get_client().list_courses()
