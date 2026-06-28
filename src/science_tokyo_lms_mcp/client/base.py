"""LMS アクセスの抽象インタフェース.

基盤 (Moodle / その他) に依存しない契約をここで定義する．
Moodle と判明した場合は Web Services API 実装を，それ以外なら
ブラウザ巡回による実装を，この :class:`LMSClient` に適合させて差し替える．
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from science_tokyo_lms_mcp.models import (
    Announcement,
    Assignment,
    Course,
    Material,
    SubmissionConstraints,
)


@runtime_checkable
class LMSClient(Protocol):
    """LMS への読み取りアクセスを抽象化したプロトコル."""

    async def list_courses(self) -> list[Course]:
        """履修中コースの一覧を取得する.

        Returns:
            コースの一覧．
        """
        ...

    async def list_materials(self, course_id: str) -> list[Material]:
        """指定コースの講義資料一覧を取得する.

        Args:
            course_id: コースの識別子．

        Returns:
            講義資料の一覧．
        """
        ...

    async def download_material(self, material: Material, dest_dir: Path) -> Path:
        """講義資料をダウンロードする.

        Args:
            material: ダウンロード対象の資料．
            dest_dir: 保存先ディレクトリ．

        Returns:
            保存したファイルのパス．
        """
        ...

    async def list_assignments(self, course_id: str | None = None) -> list[Assignment]:
        """課題と締切の一覧を取得する.

        Args:
            course_id: コース識別子．``None`` なら全コース横断．

        Returns:
            課題の一覧．
        """
        ...

    async def list_announcements(self, course_id: str | None = None) -> list[Announcement]:
        """お知らせ・休講情報の一覧を取得する.

        Args:
            course_id: コース識別子．``None`` なら全コース横断．

        Returns:
            お知らせの一覧．
        """
        ...

    async def get_assignment_detail(
        self, assignment_id: str
    ) -> tuple[Assignment, SubmissionConstraints]:
        """指定課題の詳細 (説明文) と提出制約を取得する.

        Args:
            assignment_id: 課題 (assignment) の ID．

        Returns:
            課題と提出制約の組．
        """
        ...

    async def submit_assignment_files(self, assignment_id: str, file_paths: list[Path]) -> bool:
        """ファイルを課題に提出する.

        Args:
            assignment_id: 課題 (assignment) の ID．
            file_paths: 提出するローカルファイル．

        Returns:
            採点提出まで確定したら ``True``，保存のみなら ``False``．
        """
        ...
