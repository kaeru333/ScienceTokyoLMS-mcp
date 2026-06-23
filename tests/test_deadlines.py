"""締切判定ロジックの単体テスト."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from science_tokyo_lms_mcp.models import Assignment
from science_tokyo_lms_mcp.tools.deadlines import _due_within

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 6, 22, 12, 0, tzinfo=JST)
HORIZON = NOW + timedelta(days=7)


def _assignment(due: datetime | None, *, submitted: bool = False) -> Assignment:
    return Assignment(id="a", course_id="c", title="課題", due_at=due, submitted=submitted)


def test_due_within_range() -> None:
    assignment = _assignment(NOW + timedelta(days=3))
    assert _due_within(assignment, NOW, HORIZON) is True


def test_due_beyond_horizon_excluded() -> None:
    assignment = _assignment(NOW + timedelta(days=10))
    assert _due_within(assignment, NOW, HORIZON) is False


def test_past_due_excluded() -> None:
    assignment = _assignment(NOW - timedelta(days=1))
    assert _due_within(assignment, NOW, HORIZON) is False


def test_submitted_excluded() -> None:
    assignment = _assignment(NOW + timedelta(days=3), submitted=True)
    assert _due_within(assignment, NOW, HORIZON) is False


def test_no_due_date_excluded() -> None:
    assignment = _assignment(None)
    assert _due_within(assignment, NOW, HORIZON) is False


def test_naive_due_treated_as_jst() -> None:
    naive = (NOW + timedelta(days=2)).replace(tzinfo=None)
    assignment = _assignment(naive)
    assert _due_within(assignment, NOW, HORIZON) is True
