"""LMS から取得するデータのモデル定義.

すべて不変 (frozen) な Pydantic モデルとし，副作用のない受け渡しを行う．
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    """不変モデルの共通基底."""

    model_config = ConfigDict(frozen=True)


class Course(_Frozen):
    """履修中コースを表す."""

    id: str = Field(description="コースの一意な識別子.")
    name: str = Field(description="コース名.")
    code: str | None = Field(default=None, description="科目コード.")
    url: str | None = Field(default=None, description="コースページの URL.")


class MaterialKind(StrEnum):
    """講義資料の種別."""

    FILE = "file"
    URL = "url"
    PAGE = "page"
    OTHER = "other"


class Material(_Frozen):
    """講義資料 (ファイル・リンク等) を表す."""

    id: str = Field(description="資料の一意な識別子.")
    course_id: str = Field(description="所属コースの識別子.")
    title: str = Field(description="資料のタイトル.")
    kind: MaterialKind = Field(default=MaterialKind.FILE, description="資料の種別.")
    filename: str | None = Field(default=None, description="ファイル名 (ファイルの場合).")
    url: str | None = Field(default=None, description="ダウンロード・参照先 URL.")
    updated_at: datetime | None = Field(default=None, description="最終更新日時.")


class Assignment(_Frozen):
    """課題と締切を表す."""

    id: str = Field(description="課題の一意な識別子.")
    course_id: str = Field(description="所属コースの識別子.")
    title: str = Field(description="課題のタイトル.")
    due_at: datetime | None = Field(default=None, description="提出締切日時.")
    submitted: bool = Field(default=False, description="提出済みかどうか.")
    url: str | None = Field(default=None, description="課題ページの URL.")
    intro: str | None = Field(default=None, description="課題の説明文 (HTML 除去済み).")


class SubmissionConstraints(_Frozen):
    """課題のファイル提出制約 (Moodle の課題設定に由来)."""

    file_types: tuple[str, ...] = Field(
        default=(),
        description="許可拡張子 (小文字・ドット付き). 空なら制限なし. 例: ('.pdf', '.docx').",
    )
    file_types_raw: str = Field(
        default="",
        description="filetypeslist の生の値 (グループ名等を含むため Claude への提示用).",
    )
    max_size_bytes: int = Field(
        default=0,
        description="1 ファイルの最大サイズ (バイト). 0 は無制限ないしコース上限.",
    )
    max_files: int = Field(default=1, description="提出可能なファイル数.")
    submission_drafts: bool = Field(
        default=False,
        description="True なら下書き方式で，採点提出 (submit_for_grading) が必要.",
    )
    require_statement: bool = Field(default=False, description="提出規約への同意が必要か.")
    file_plugin_enabled: bool = Field(default=True, description="ファイル提出プラグインが有効か.")


class FileCheck(_Frozen):
    """提出予定ファイル 1 件のローカル検査結果."""

    path: str = Field(description="ローカルファイルのパス.")
    filename: str = Field(description="ファイル名.")
    exists: bool = Field(description="ファイルが存在するか.")
    size_bytes: int = Field(default=0, description="ファイルサイズ (バイト).")
    extension: str = Field(default="", description="拡張子 (小文字・ドット付き).")
    extension_ok: bool = Field(default=True, description="拡張子が許可されているか.")
    size_ok: bool = Field(default=True, description="サイズが上限以内か.")
    issues: tuple[str, ...] = Field(default=(), description="検出された問題点の説明 (日本語).")


class SubmissionPlan(_Frozen):
    """課題提出のプレビュー兼結果.

    confirm=False ではプレビュー (Moodle へ書き込みなし)，confirm=True では
    実提出の結果を表す．Claude は本モデルと各ファイルの中身を突き合わせて
    課題の意図に合っているか判断する．
    """

    assignment_id: str = Field(description="課題 (assignment) の ID.")
    assignment_title: str = Field(description="課題のタイトル.")
    assignment_intro: str | None = Field(default=None, description="課題の説明文 (HTML 除去済み).")
    constraints: SubmissionConstraints = Field(description="課題のファイル提出制約.")
    files: tuple[FileCheck, ...] = Field(description="各提出予定ファイルの検査結果.")
    all_ok: bool = Field(description="全ファイルが提出可能な状態か.")
    confirmed: bool = Field(default=False, description="実際に提出したか (False はプレビュー).")
    submitted_for_grading: bool = Field(default=False, description="採点提出まで確定したか.")
    notes: tuple[str, ...] = Field(
        default=(), description="Claude / ユーザーへの注意書き (確認を促す文言)."
    )


class Announcement(_Frozen):
    """お知らせ・休講情報を表す."""

    id: str = Field(description="お知らせの一意な識別子.")
    title: str = Field(description="件名.")
    course_id: str | None = Field(default=None, description="関連コースの識別子.")
    posted_at: datetime | None = Field(default=None, description="掲載日時.")
    body: str | None = Field(default=None, description="本文.")
