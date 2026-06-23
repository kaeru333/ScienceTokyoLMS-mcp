"""MCP ツール群.

ドメインごとにモジュールを分け，各モジュールの ``register`` で
FastMCP インスタンスにツールを登録する．
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from science_tokyo_lms_mcp.tools import announcements, courses, deadlines, materials

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    """全ツールを FastMCP インスタンスに登録する.

    Args:
        mcp: 登録先の FastMCP インスタンス．
    """
    courses.register(mcp)
    materials.register(mcp)
    deadlines.register(mcp)
    announcements.register(mcp)
