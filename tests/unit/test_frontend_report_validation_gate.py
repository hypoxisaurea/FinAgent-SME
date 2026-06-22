from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from frontend.views import report


def test_report_render_stops_when_validation_is_blocked(monkeypatch) -> None:
    error = MagicMock()
    caption = MagicMock()
    fake_st = SimpleNamespace(
        session_state=SimpleNamespace(
            last_result={
                "status": "failed",
                "code": "VALIDATION_FAILED",
                "message": "검증 실패로 결과가 차단되었습니다.",
                "context": {"validation_gate_status": "blocked"},
            }
        ),
        error=error,
        caption=caption,
    )
    build_view_model = MagicMock()

    monkeypatch.setattr(report, "st", fake_st)
    monkeypatch.setattr(report, "build_report_view_model", build_view_model)

    report.render()

    error.assert_called_once_with("검증 실패로 결과가 차단되었습니다.")
    caption.assert_called_once_with("오류 코드: VALIDATION_FAILED")
    build_view_model.assert_not_called()


def test_validation_blocked_detection_accepts_gate_metadata() -> None:
    assert report._is_validation_blocked(
        {"context": {"validation_gate_status": "blocked"}}
    )
    assert not report._is_validation_blocked(
        {"status": "partial", "context": {"validation_gate_status": "passed"}}
    )
