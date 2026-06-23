"""データモデルの単体テスト."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from science_tokyo_lms_mcp.models import Assignment, Course, Material, MaterialKind


def test_course_construction() -> None:
    course = Course(id="1", name="代数学")
    assert course.id == "1"
    assert course.code is None


def test_course_is_immutable() -> None:
    course = Course(id="1", name="代数学")
    with pytest.raises(ValidationError):
        course.name = "幾何学"  # type: ignore[misc]


def test_material_default_kind() -> None:
    material = Material(id="m1", course_id="1", title="第1回資料")
    assert material.kind is MaterialKind.FILE


def test_assignment_defaults() -> None:
    assignment = Assignment(id="a1", course_id="1", title="レポート1")
    assert assignment.submitted is False
    assert assignment.due_at is None


def test_assignment_with_due_date() -> None:
    due = datetime(2026, 7, 1, 23, 59)
    assignment = Assignment(id="a1", course_id="1", title="レポート1", due_at=due)
    assert assignment.due_at == due
