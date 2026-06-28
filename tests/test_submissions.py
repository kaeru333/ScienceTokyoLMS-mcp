"""課題提出ロジックの単体テスト (ネットワーク非依存)."""

from pathlib import Path

from science_tokyo_lms_mcp.client.moodle_client import _parse_constraints, _parse_filetypes
from science_tokyo_lms_mcp.models import SubmissionConstraints
from science_tokyo_lms_mcp.tools.submissions import _check_files


def test_parse_filetypes_empty_means_no_limit() -> None:
    assert _parse_filetypes("") == ()
    assert _parse_filetypes("   ") == ()


def test_parse_filetypes_dotted_and_bare() -> None:
    assert _parse_filetypes(".pdf,.docx") == (".pdf", ".docx")
    assert _parse_filetypes("pdf docx") == (".pdf", ".docx")


def test_parse_filetypes_dedups_preserving_order() -> None:
    assert _parse_filetypes("pdf, .pdf ; pdf") == (".pdf",)


def test_parse_filetypes_group_expansion() -> None:
    result = _parse_filetypes("document")
    assert ".pdf" in result
    assert ".docx" in result


def test_parse_constraints_extracts_file_config() -> None:
    raw = {
        "submissiondrafts": "1",
        "requiresubmissionstatement": "0",
        "configs": [
            {
                "plugin": "file",
                "subtype": "assignsubmission_file",
                "name": "filetypeslist",
                "value": ".pdf",
            },
            {
                "plugin": "file",
                "subtype": "assignsubmission_file",
                "name": "maxfilesubmissions",
                "value": "3",
            },
            {
                "plugin": "file",
                "subtype": "assignsubmission_file",
                "name": "maxsubmissionsizebytes",
                "value": "1048576",
            },
        ],
    }
    constraints = _parse_constraints(raw)
    assert constraints.file_types == (".pdf",)
    assert constraints.file_types_raw == ".pdf"
    assert constraints.max_files == 3
    assert constraints.max_size_bytes == 1048576
    assert constraints.submission_drafts is True
    assert constraints.require_statement is False


def test_parse_constraints_defaults_when_no_configs() -> None:
    constraints = _parse_constraints({})
    assert constraints.file_types == ()
    assert constraints.max_files == 1
    assert constraints.max_size_bytes == 0
    assert constraints.submission_drafts is False


def test_check_files_flags_missing(tmp_path: Path) -> None:
    constraints = SubmissionConstraints(file_types=(".pdf",))
    checks = _check_files([str(tmp_path / "nope.pdf")], constraints)
    assert checks[0].exists is False
    assert checks[0].issues


def test_check_files_flags_bad_extension(tmp_path: Path) -> None:
    bad = tmp_path / "a.txt"
    bad.write_text("hello")
    constraints = SubmissionConstraints(file_types=(".pdf",))
    checks = _check_files([str(bad)], constraints)
    assert checks[0].exists is True
    assert checks[0].extension_ok is False
    assert checks[0].issues


def test_check_files_flags_oversize(tmp_path: Path) -> None:
    big = tmp_path / "a.pdf"
    big.write_bytes(b"x" * 100)
    constraints = SubmissionConstraints(file_types=(".pdf",), max_size_bytes=10)
    checks = _check_files([str(big)], constraints)
    assert checks[0].size_ok is False
    assert checks[0].issues


def test_check_files_ok(tmp_path: Path) -> None:
    good = tmp_path / "report.pdf"
    good.write_bytes(b"%PDF-1.4 ...")
    constraints = SubmissionConstraints(file_types=(".pdf",))
    checks = _check_files([str(good)], constraints)
    assert checks[0].exists is True
    assert checks[0].extension_ok is True
    assert checks[0].size_ok is True
    assert not checks[0].issues


def test_check_files_no_type_limit_accepts_any(tmp_path: Path) -> None:
    good = tmp_path / "a.bin"
    good.write_bytes(b"data")
    constraints = SubmissionConstraints(file_types=())
    checks = _check_files([str(good)], constraints)
    assert checks[0].extension_ok is True
    assert not checks[0].issues
