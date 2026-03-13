"""Tests for analysis mode configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from code_context_agent.config import AnalysisMode, Settings


class TestAnalysisMode:
    def test_enum_values(self) -> None:
        assert AnalysisMode.STANDARD == "standard"
        assert AnalysisMode.FULL == "full"

    def test_str_enum(self) -> None:
        assert str(AnalysisMode.FULL) == "full"
        assert f"mode={AnalysisMode.FULL}" == "mode=full"


class TestSettingsFullMode:
    def test_full_max_duration_default(self) -> None:
        s = Settings()
        assert s.full_max_duration == 3600  # noqa: PLR2004

    def test_full_max_duration_range(self) -> None:
        s = Settings(full_max_duration=300)
        assert s.full_max_duration == 300  # noqa: PLR2004
        with pytest.raises(ValidationError):
            Settings(full_max_duration=100)

    def test_full_max_turns_default(self) -> None:
        s = Settings()
        assert s.full_max_turns == 3000  # noqa: PLR2004

    def test_full_mode_settings_override(self) -> None:
        """model_copy to override for full mode."""
        s = Settings()
        full = s.model_copy(
            update={
                "agent_max_duration": s.full_max_duration,
                "agent_max_turns": s.full_max_turns,
                "lsp_max_files": 50_000,
            },
        )
        assert full.agent_max_duration == 3600  # noqa: PLR2004
        assert full.agent_max_turns == 3000  # noqa: PLR2004
        assert full.lsp_max_files == 50_000  # noqa: PLR2004
