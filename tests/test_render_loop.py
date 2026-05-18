"""Tests for the render/fix loop error-handling paths in CourseWorkflow."""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.rendering.render import TTSSynthesisError
from src.workflow import CourseWorkflow


@pytest.fixture()
def workflow() -> CourseWorkflow:
    with patch("src.workflow.make_openrouter_llm"), patch("src.workflow.ManimScriptGenerator"):
        return CourseWorkflow(model="test/model")


def _make_ctx(tmp_path: Path, *, skip_review: bool = False) -> dict:
    return {
        "slug": "test-lesson",
        "prompt_topic": "Test Topic",
        "out": tmp_path,
        "skip_review": skip_review,
        "final_quality": False,
        "video_hash": "abc123",
    }


class TestTTSSynthesisError:
    def test_tts_error_re_raised_without_calling_fixer(
        self, workflow: CourseWorkflow, tmp_path: Path
    ) -> None:
        """TTSSynthesisError must propagate immediately — the script fixer must not be called."""
        script_path = tmp_path / "script.py"
        script_path.write_text("# dummy")
        ctx = _make_ctx(tmp_path, skip_review=True)

        from src.core.llm_metrics import UsageTracker

        tracker = UsageTracker()
        tts_error = TTSSynthesisError("MPS out of memory")

        with (
            patch.object(workflow, "_run_single_iteration", side_effect=tts_error),
            patch.object(workflow, "_handle_render_error") as mock_fixer,
            pytest.raises(TTSSynthesisError),
        ):
            workflow._render_loop(ctx, script_path, tracker)  # type: ignore[arg-type]

        mock_fixer.assert_not_called()

    def test_manim_error_calls_fixer(self, workflow: CourseWorkflow, tmp_path: Path) -> None:
        """A plain RuntimeError from Manim must be forwarded to the script fixer."""
        script_path = tmp_path / "script.py"
        script_path.write_text("# dummy")
        ctx = _make_ctx(tmp_path, skip_review=True)

        from src.core.llm_metrics import LLMUsage, UsageTracker

        tracker = UsageTracker()
        manim_error = RuntimeError("Manim render failed:\nNameError: name 'foo' is not defined")
        good_video = tmp_path / "ok.mp4"
        good_video.write_bytes(b"")

        call_count = 0

        def _side_effect(*_a: object, **_kw: object) -> Path:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise manim_error
            return good_video

        with (
            patch.object(workflow, "_run_single_iteration", side_effect=_side_effect),
            patch.object(workflow, "_handle_render_error", return_value=LLMUsage()) as mock_fixer,
        ):
            workflow._render_loop(ctx, script_path, tracker)  # type: ignore[arg-type]

        mock_fixer.assert_called_once()
