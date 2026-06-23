"""講義資料関連の MCP ツール."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from science_tokyo_lms_mcp.client import get_client
from science_tokyo_lms_mcp.config import get_settings
from science_tokyo_lms_mcp.models import Material

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    """講義資料関連ツールを登録する.

    Args:
        mcp: 登録先の FastMCP インスタンス．
    """

    @mcp.tool()
    async def list_materials(course_id: str) -> list[Material]:
        """指定コースの講義資料一覧を取得する.

        Args:
            course_id: コースの識別子．

        Returns:
            講義資料の一覧．
        """
        return await get_client().list_materials(course_id)

    @mcp.tool()
    async def download_material(
        course_id: str,
        material_id: str,
        dest_dir: str | None = None,
    ) -> str:
        """講義資料をダウンロードし，保存先パスを返す.

        Args:
            course_id: コースの識別子．
            material_id: ダウンロードする資料の識別子．
            dest_dir: 保存先ディレクトリ．省略時は設定値を用いる．

        Returns:
            保存したファイルの絶対パス (文字列)．

        Raises:
            ValueError: 指定した資料が見つからない場合．
        """
        client = get_client()
        materials = await client.list_materials(course_id)
        target = next((m for m in materials if m.id == material_id), None)
        if target is None:
            msg = f"資料が見つかりません: course_id={course_id}, material_id={material_id}"
            raise ValueError(msg)

        dest = Path(dest_dir) if dest_dir else Path(get_settings().download_dir)
        dest.mkdir(parents=True, exist_ok=True)
        saved = await client.download_material(target, dest)
        return str(saved.resolve())
