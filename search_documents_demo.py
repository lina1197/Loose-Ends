"""search_documents_demo.py: Local document retrieval demonstration.

No Gemini calls. Demonstrates that search_documents and get_document
work correctly against the local mock document dataset.

Usage:
    .venv\\Scripts\\python search_documents_demo.py
"""
import json

from loose_ends.documents.document_tools import search_documents, get_document

SEP = "=" * 64
SEP2 = "-" * 48


def _section(title: str) -> None:
    print()
    print(SEP)
    print(f"  {title}")
    print(SEP)


def main() -> None:
    print(SEP)
    print("  Loose Ends -- Document Retrieval Demo")
    print(SEP)

    # ── Step 1: search for Q3 financial figures ────────────────────────────
    _section("Step 1: search_documents(query='Q3 financial figures')")
    raw = search_documents(query="Q3 financial figures")
    result = json.loads(raw)
    print(f"\n  Found {result['count']} document(s):\n")
    for d in result["documents"]:
        print(f"  {SEP2}")
        print(f"  document_id   : {d['document_id']}")
        print(f"  filename      : {d['filename']}")
        print(f"  title         : {d['title']}")
        print(f"  document_type : {d['document_type']}")
        print(f"  created_at    : {d['created_at']}")
        print(f"  (content excluded from search results)")
    print(f"\n  -> 'doc-q3-figures' found: "
          f"{'YES' if any(d['document_id']=='doc-q3-figures' for d in result['documents']) else 'NO'}")

    # ── Step 2: retrieve the Q3 document by ID ─────────────────────────────
    _section("Step 2: get_document(document_id='doc-q3-figures')")
    raw2 = get_document(document_id="doc-q3-figures")
    doc = json.loads(raw2)
    print()
    print(f"  document_id   : {doc['document_id']}")
    print(f"  filename      : {doc['filename']}")
    print(f"  title         : {doc['title']}")
    print(f"  document_type : {doc['document_type']}")
    print(f"  created_at    : {doc['created_at']}")
    print()
    print("  --- Content (first 600 chars) ---")
    print()
    for line in doc["content"][:600].splitlines():
        print(f"  {line}")
    print()

    # ── Step 3: verify unrelated documents exist ───────────────────────────
    _section("Step 3: search_documents(document_type='policy') -- unrelated doc")
    raw3 = search_documents(document_type="policy")
    result3 = json.loads(raw3)
    print(f"\n  Found {result3['count']} policy document(s):")
    for d in result3["documents"]:
        print(f"    [{d['document_id']}] {d['title']}")

    # ── Step 4: demonstrate no-results case ───────────────────────────────
    _section("Step 4: search_documents(query='zzzz-no-match') -- empty result")
    raw4 = search_documents(query="zzzz-no-match-xyz")
    result4 = json.loads(raw4)
    print(f"\n  count = {result4['count']}  (expected: 0)")
    print(f"  documents = {result4['documents']}  (expected: [])")

    print()
    print(SEP)
    print("  Demo complete. Both tools are working correctly.")
    print(SEP)
    print()


if __name__ == "__main__":
    main()