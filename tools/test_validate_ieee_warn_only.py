"""warn-only-gates S2: IEEE reference errors warn on stderr and exit 0."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import validate_ieee_refs


def test_ieee_errors_warn_and_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = SimpleNamespace(errors=["IEEE: falta [1]"], warnings=[])
    with (
        patch.object(sys, "argv", ["validate_ieee_refs.py", str(tmp_path)]),
        patch("validate_ieee_refs.load_report_config", return_value=SimpleNamespace()),
        patch("validate_ieee_refs.validate_ieee", return_value=result),
    ):
        validate_ieee_refs.main()  # no SystemExit: exit 0

    captured = capsys.readouterr()
    assert captured.err == "warning: IEEE validation failed:\n- IEEE: falta [1]\n"
    assert "IEEE validation OK" not in captured.out


def test_missing_report_yml_still_fails(tmp_path: Path) -> None:
    with patch.object(sys, "argv", ["validate_ieee_refs.py", str(tmp_path / "missing")]):
        with pytest.raises(SystemExit) as exc:
            validate_ieee_refs.main()
    assert exc.value.code not in (0, None)
