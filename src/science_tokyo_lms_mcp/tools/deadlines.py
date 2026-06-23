"""課題・締切関連の MCP ツール."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from science_tokyo_lms_mcp.client import get_client
from science_tokyo_lms_mcp.models import Assignment

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_JST = ZoneInfo("Asia/Tokyo")


def _due_within(assignment: Assignment, now: datetime, horizon: datetime) -> bool:
    """課題の締切が ``now`` から ``horizon`` の範囲かつ未提出かを判定する.

    Args:
        assignment: 判定対象の課題．
        now: 現在日時 (JST)．
        horizon: 期限の上限日時 (JST)．

    Returns:
        範囲内かつ未提出なら ``True``．
    """
    if assignment.due_at is None or assignment.submitted:
        return False
    due = assignment.due_at
    if due.tzinfo is None:
        due = due.replace(tzinfo=_JST)
    return now <= due <= horizon


def register(mcp: FastMCP) -> None:
    """課題・締切関連ツールを登録する.

    Args:
        mcp: 登録先の FastMCP インスタンス．
    """

    @mcp.tool()
    async def list_assignments(course_id: str | None = None) -> list[Assignment]:
        """課題と締切の一覧を取得する.

        Args:
            course_id: コースの識別子．省略時は全コース横断．

        Returns:
            課題の一覧．
        """
        return await get_client().list_assignments(course_id)

    @mcp.tool()
    async def get_upcoming_deadlines(days: int = 7) -> list[Assignment]:
        """直近の未提出課題を締切順に取得する.

        Args:
            days: 何日先までの締切を対象とするか．

        Returns:
            締切が近い順に並べた未提出課題の一覧．
        """
        assignments = await get_client().list_assignments()
        now = datetime.now(_JST)
        horizon = now + timedelta(days=days)
        upcoming = [a for a in assignments if _due_within(a, now, horizon)]
        return sorted(upcoming, key=lambda a: a.due_at or horizon)
