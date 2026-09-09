"""Entry point for the Loose Ends Strands proof-of-concept."""
import os

from dotenv import load_dotenv

# Load .env before importing anything that reads env vars
load_dotenv()

from loose_ends.agent import build_agent  # noqa: E402


PROMPT = (
    "Please call the get_loose_ends_status tool and tell me "
    "what it returns."
)


def main() -> None:
    print("=" * 60)
    print("  Loose Ends – Strands + Gemini PoC")
    print("=" * 60)
    print(f"Prompt: {PROMPT}\n")

    agent = build_agent()
    response = agent(PROMPT)

    print("\n" + "=" * 60)
    print("  Agent response:")
    print("=" * 60)
    print(response)


if __name__ == "__main__":
    main()
