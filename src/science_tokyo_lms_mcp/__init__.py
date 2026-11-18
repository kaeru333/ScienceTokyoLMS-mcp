"""東京科学大学 Science Tokyo LMS 用 MCP サーバ.

Moodle Web Services REST API とモバイルトークン認証を用いて，
講義資料のダウンロード・課題締切の確認・課題提出などを MCP ツールとして提供する．
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("science-tokyo-lms-mcp")
except PackageNotFoundError:
    __version__ = "0.1.0b2"
