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


class Announcement(_Frozen):
    """お知らせ・休講情報を表す."""

    id: str = Field(description="お知らせの一意な識別子.")
    title: str = Field(description="件名.")
    course_id: str | None = Field(default=None, description="関連コースの識別子.")
    posted_at: datetime | None = Field(default=None, description="掲載日時.")
    body: str | None = Field(default=None, description="本文.")
