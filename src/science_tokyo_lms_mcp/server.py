"""MCP サーバのエントリポイント.

FastMCP インスタンスを構築し，全ツールを登録して stdio で起動する．
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from science_tokyo_lms_mcp.tools import register_all


def build_server() -> FastMCP:
    """ツールを登録した FastMCP サーバを構築する.

    Returns:
        構築済みの :class:`FastMCP` インスタンス．
    """
    mcp = FastMCP("science-tokyo-lms")
    register_all(mcp)
    return mcp


def main() -> None:
    """MCP サーバを stdio トランスポートで起動する."""
    build_server().run()


if __name__ == "__main__":
    main()
