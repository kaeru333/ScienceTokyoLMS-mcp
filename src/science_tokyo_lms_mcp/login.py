"""初回トークン取得用 CLI.

ブラウザで SSO ログイン (MFA 含む) を行い，Moodle モバイルトークンを取得して
keyring に保管する．以降は MCP サーバがそのトークンで Web Services を呼ぶ．

実行例::

    uv run science-tokyo-lms-login
"""

from __future__ import annotations

import asyncio

from science_tokyo_lms_mcp.auth.token import acquire_token, save_token
from science_tokyo_lms_mcp.config import get_settings


async def _run() -> None:
    """トークンを取得して保存する."""
    settings = get_settings()
    token = await acquire_token(settings)
    save_token(token, settings)
    print("トークンを取得・保存しました．MCP サーバから利用できます．")


def main() -> None:
    """エントリポイント."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
