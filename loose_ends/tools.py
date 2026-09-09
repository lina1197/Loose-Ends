"""Custom Strands tools for Loose Ends."""
import sys

from strands import tool


@tool
def get_loose_ends_status() -> str:
    """Return the current operational status of the Loose Ends agent system.

    Call this tool to confirm that the Loose Ends agent is running and its
    custom tooling is reachable.  It performs no network calls and returns a
    static demonstration string.
    """
    # Emit a highly visible console marker so it is obvious the tool was called.
    print(
        "\n"
        + "=" * 60 + "\n"
        + "  [TOOL CALLED] get_loose_ends_status\n"
        + "=" * 60 + "\n",
        file=sys.stdout,
        flush=True,
    )
    return "Loose Ends is running locally."
