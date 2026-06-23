"""LMS クライアントパッケージ.

Science Tokyo LMS は Moodle 基盤と判明したため，既定では Web Services API を
用いる :class:`MoodleClient` を提供する．:class:`PlaywrightLMSClient` は
スクレイピング方式のフォールバック実装として残している．
"""

from __future__ import annotations

from functools import lru_cache

from science_tokyo_lms_mcp.client.base import LMSClient
from science_tokyo_lms_mcp.client.moodle_client import MoodleClient
from science_tokyo_lms_mcp.client.playwright_client import PlaywrightLMSClient

__all__ = ["LMSClient", "MoodleClient", "PlaywrightLMSClient", "get_client"]


@lru_cache(maxsize=1)
def get_client() -> LMSClient:
    """既定の LMS クライアントを取得する (プロセス内でキャッシュ).

    Returns:
        :class:`LMSClient` プロトコルに適合するクライアント．
    """
    return MoodleClient()
