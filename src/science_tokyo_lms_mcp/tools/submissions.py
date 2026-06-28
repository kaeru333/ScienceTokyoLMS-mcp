"""課題のファイル提出関連の MCP ツール.

提出ツールは 2 フェーズ構成とする．confirm=False (既定) では Moodle へ一切
書き込まず，課題の説明文・提出制約・各ファイルの検査結果のみを返す．Claude は
その結果と各ファイルの中身 (Read で開いて目視) を突き合わせ，課題の意図に
合っているかを判断する．問題なければ confirm=True で再度呼び出して実提出する．

「合っているかの判定」はサーバ側では行わない．判断材料を返すことに徹する．
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from science_tokyo_lms_mcp.client import get_client
from science_tokyo_lms_mcp.models import FileCheck, SubmissionConstraints, SubmissionPlan

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


_CONFIRM_WARNING = (
    "これは課題への実提出です．confirm=True で実行すると Moodle に提出され，"
    "課題設定によっては取り消せません．提出前に各ファイルを開いて内容を確認し，"
    "課題の説明文 (assignment_intro) と一致しているか必ず確かめてください．"
)


def _check_files(
    file_paths: list[str], constraints: SubmissionConstraints
) -> tuple[FileCheck, ...]:
    """提出予定ファイルをローカル検査する (副作用なし).

    Args:
        file_paths: 検査するファイルパスの一覧．
        constraints: 課題のファイル提出制約．

    Returns:
        各ファイルの検査結果．
    """
    checks: list[FileCheck] = []
    for raw in file_paths:
        path = Path(raw).expanduser()
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        ext = path.suffix.lower()
        ext_ok = (not constraints.file_types) or (ext in constraints.file_types)
        size_ok = constraints.max_size_bytes == 0 or size <= constraints.max_size_bytes

        issues: list[str] = []
        if not exists:
            issues.append("ファイルが存在しません．")
        if exists and not ext_ok:
            allowed = ", ".join(constraints.file_types)
            issues.append(f"拡張子 {ext} は許可されていません (許可: {allowed}).")
        if exists and not size_ok:
            issues.append(
                f"サイズ {size} バイトが上限 {constraints.max_size_bytes} バイトを超えています．"
            )

        checks.append(
            FileCheck(
                path=str(path.resolve()) if exists else str(path),
                filename=path.name,
                exists=exists,
                size_bytes=size,
                extension=ext,
                extension_ok=ext_ok,
                size_ok=size_ok,
                issues=tuple(issues),
            )
        )
    return tuple(checks)


def _build_notes(
    checks: tuple[FileCheck, ...], constraints: SubmissionConstraints
) -> tuple[str, ...]:
    """プレビュー時の注意書き (Claude / ユーザーへの確認喚起) を組み立てる.

    Args:
        checks: 各ファイルの検査結果．
        constraints: 課題のファイル提出制約．

    Returns:
        注意書きのタプル．
    """
    notes: list[str] = [_CONFIRM_WARNING]
    if not constraints.file_plugin_enabled:
        notes.append("この課題はファイル提出が無効になっています．")
    if len(checks) > constraints.max_files:
        notes.append(f"ファイル数 {len(checks)} が上限 {constraints.max_files} を超えています．")
    if constraints.file_types_raw and any(not c.extension_ok for c in checks):
        notes.append(
            "拡張子の許可リスト (filetypeslist) は "
            f"'{constraints.file_types_raw}' です．グループ名を含む場合は"
            "判定が近似的なため，内容を確認してください．"
        )
    if constraints.submission_drafts:
        notes.append("この課題は下書き方式です．confirm=True で採点提出まで確定します．")
    else:
        notes.append("この課題は保存=提出です．confirm=True で提出が完了します．")
    return tuple(notes)


def register(mcp: FastMCP) -> None:
    """課題提出関連ツールを登録する.

    Args:
        mcp: 登録先の FastMCP インスタンス．
    """

    @mcp.tool()
    async def submit_assignment_files(
        assignment_id: str,
        file_paths: list[str],
        confirm: bool = False,
    ) -> SubmissionPlan:
        """課題にファイルを提出する (2 段階: 既定はプレビュー).

        confirm=False (既定) では Moodle へ一切書き込まず，課題の説明文・提出制約・
        各ファイルの検査結果のみを返す．**この結果を受け取ったら，各ファイルを Read で
        開いて内容を確認し，課題の説明文 (assignment_intro) と突き合わせて，提出物が
        課題の意図に合っているかを必ず判断すること．** 問題がなければ confirm=True で
        同じ引数で再度呼び出すと実提出する．

        Args:
            assignment_id: 課題 (assignment) の ID．list_assignments で取得できる．
            file_paths: 提出するローカルファイルのパス (複数可)．
            confirm: True で実提出．False (既定) はプレビューのみ (書き込みなし)．

        Returns:
            提出プレビュー，または提出結果 (:class:`SubmissionPlan`)．

        Raises:
            ValueError: confirm=True だが検査に通らないファイルや個数超過がある場合．
        """
        client = get_client()
        assignment, constraints = await client.get_assignment_detail(assignment_id)
        checks = _check_files(file_paths, constraints)
        all_ok = bool(checks) and all(c.exists and c.extension_ok and c.size_ok for c in checks)
        notes = _build_notes(checks, constraints)

        if not confirm:
            return SubmissionPlan(
                assignment_id=assignment.id,
                assignment_title=assignment.title,
                assignment_intro=assignment.intro,
                constraints=constraints,
                files=checks,
                all_ok=all_ok,
                confirmed=False,
                submitted_for_grading=False,
                notes=notes,
            )

        # confirm=True: サーバ側で再検証してから提出する (直接呼ばれても安全に)．
        if not all_ok:
            problems = "; ".join(issue for c in checks for issue in c.issues)
            msg = f"提出できないファイルがあります: {problems}"
            raise ValueError(msg)
        if len(checks) > constraints.max_files:
            msg = f"ファイル数が上限 {constraints.max_files} を超えています．"
            raise ValueError(msg)

        submitted = await client.submit_assignment_files(
            assignment_id, [Path(c.path) for c in checks]
        )
        result_note = "提出が完了しました．" + (
            "採点提出まで確定しました．" if submitted else "保存しました (保存=提出)．"
        )
        return SubmissionPlan(
            assignment_id=assignment.id,
            assignment_title=assignment.title,
            assignment_intro=assignment.intro,
            constraints=constraints,
            files=checks,
            all_ok=True,
            confirmed=True,
            submitted_for_grading=submitted,
            notes=(result_note,),
        )
