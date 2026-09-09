"""Unit tests for Loose Ends custom Strands tools.

These tests exercise the tool function itself without any Gemini call.
"""
from loose_ends.tools import get_loose_ends_status


def test_get_loose_ends_status_returns_expected_string():
    """The tool must return the expected status string."""
    # Strands @tool-decorated functions are still callable directly in tests.
    result = get_loose_ends_status()
    assert result == "Loose Ends is running locally.", (
        f"Unexpected return value: {result!r}"
    )


def test_get_loose_ends_status_returns_str():
    """The tool must return a plain str."""
    result = get_loose_ends_status()
    assert isinstance(result, str)
