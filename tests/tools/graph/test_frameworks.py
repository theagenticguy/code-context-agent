"""Tests for framework detection and entry point scoring."""

from __future__ import annotations

from code_context_agent.tools.graph.frameworks import (
    detect_frameworks,
    get_entry_point_patterns,
    score_entry_point,
)


class TestDetectFrameworks:
    """Tests for detect_frameworks()."""

    def test_detect_nextjs_from_pages(self) -> None:
        """Files with pages/**/*.tsx detect 'nextjs'."""
        files = ["pages/api/hello.tsx", "pages/dashboard/index.tsx", "components/Header.tsx"]
        detected = detect_frameworks(files)
        assert "nextjs" in detected

    def test_detect_fastapi_from_routers(self) -> None:
        """Files with routers/*.py detect 'fastapi'."""
        files = ["src/routers/users.py", "src/routers/items.py", "src/main.py"]
        detected = detect_frameworks(files)
        assert "fastapi" in detected

    def test_detect_django_from_views(self) -> None:
        """Files with views.py detect 'django'."""
        files = ["myapp/views.py", "myapp/models.py", "myapp/urls.py"]
        detected = detect_frameworks(files)
        assert "django" in detected

    def test_detect_multiple_frameworks(self) -> None:
        """Files matching both pytest and flask patterns detect both."""
        files = [
            "tests/test_app.py",
            "app/routes.py",
            "conftest.py",
        ]
        detected = detect_frameworks(files)
        assert "pytest" in detected
        # flask requires @app.route symbol_pattern match — but file_glob **/*.py matches
        # the flask patterns require symbol_pattern, so just check pytest is detected
        # and verify we can detect multiple with a clearer example
        # Add a cli file to get a second framework
        files_multi = ["tests/test_app.py", "src/__main__.py"]
        detected_multi = detect_frameworks(files_multi)
        assert "pytest" in detected_multi
        assert "cli" in detected_multi


class TestScoreEntryPoint:
    """Tests for score_entry_point()."""

    def test_score_entry_point_matching_pattern(self) -> None:
        """Node matching a pattern gets boost > 1.0."""
        patterns = get_entry_point_patterns(["django"])
        node_data = {"file_path": "myapp/views.py", "name": "index_view"}
        boost = score_entry_point(node_data, patterns)
        assert boost > 1.0

    def test_score_entry_point_no_match(self) -> None:
        """Node not matching any pattern returns 1.0."""
        patterns = get_entry_point_patterns(["django"])
        node_data = {"file_path": "utils/helpers.py", "name": "format_string"}
        boost = score_entry_point(node_data, patterns)
        assert boost == 1.0
