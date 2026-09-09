"""Unit and integration tests for the document data model, repository, and tools.

All tests are deterministic and do NOT call Gemini.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from loose_ends.documents.document import Document
from loose_ends.documents.repository import DocumentRepository
from loose_ends.documents.document_tools import search_documents, get_document, _repo

TOTAL_DOCUMENTS = 4
_BASE = datetime(2027, 9, 1, 8, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _search(**kwargs) -> dict:
    return json.loads(search_documents(**kwargs))


def _get(doc_id: str) -> dict:
    return json.loads(get_document(document_id=doc_id))


# ---------------------------------------------------------------------------
# Integration: tool importability
# ---------------------------------------------------------------------------

class TestToolImport:
    def test_search_documents_importable(self):
        from loose_ends.documents.document_tools import search_documents as t
        assert t is not None

    def test_get_document_importable(self):
        from loose_ends.documents.document_tools import get_document as t
        assert t is not None

    def test_search_documents_callable(self):
        assert callable(search_documents)

    def test_get_document_callable(self):
        assert callable(get_document)


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------

class TestDocumentModel:
    def _make(self, **overrides) -> Document:
        defaults = dict(
            document_id="d-001",
            filename="test.pdf",
            title="Test Doc",
            content="Some content here.",
            document_type="financial",
            created_at=_BASE,
            updated_at=_BASE,
        )
        defaults.update(overrides)
        return Document(**defaults)

    def test_valid_document_creates_successfully(self):
        d = self._make()
        assert d.document_id == "d-001"

    def test_empty_document_id_raises(self):
        with pytest.raises(ValueError, match="document_id"):
            self._make(document_id="")

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title"):
            self._make(title="")

    def test_naive_created_at_raises(self):
        with pytest.raises(ValueError, match="created_at"):
            self._make(created_at=datetime(2027, 1, 1))

    def test_to_dict_includes_content(self):
        d = self._make(content="Secret numbers")
        assert "content" in d.to_dict()
        assert d.to_dict()["content"] == "Secret numbers"

    def test_to_summary_dict_excludes_content(self):
        d = self._make(content="Secret numbers")
        assert "content" not in d.to_summary_dict()

    def test_to_summary_dict_has_required_keys(self):
        d = self._make()
        keys = d.to_summary_dict().keys()
        for k in ("document_id", "filename", "title", "document_type",
                   "created_at", "updated_at"):
            assert k in keys

    def test_from_dict_round_trip(self):
        d = self._make()
        restored = Document.from_dict(d.to_dict())
        assert restored == d

    def test_is_frozen(self):
        d = self._make()
        with pytest.raises((AttributeError, TypeError)):
            d.title = "changed"  # type: ignore


# ---------------------------------------------------------------------------
# Repository loading
# ---------------------------------------------------------------------------

class TestRepositoryLoading:
    def test_default_repo_loads_documents(self):
        repo = DocumentRepository()
        assert len(repo) == TOTAL_DOCUMENTS

    def test_loaded_items_are_document_instances(self):
        repo = DocumentRepository()
        for doc in repo.all():
            assert isinstance(doc, Document)

    def test_timestamps_are_utc_aware(self):
        repo = DocumentRepository()
        for doc in repo.all():
            assert doc.created_at.tzinfo is not None
            assert doc.updated_at.tzinfo is not None

    def test_all_returns_independent_list(self):
        repo = DocumentRepository()
        snapshot = repo.all()
        snapshot.clear()
        assert len(repo) == TOTAL_DOCUMENTS

    def test_get_by_valid_id(self):
        repo = DocumentRepository()
        doc = repo.get("doc-q3-figures")
        assert doc is not None
        assert doc.document_id == "doc-q3-figures"

    def test_get_unknown_id_returns_none(self):
        repo = DocumentRepository()
        assert repo.get("does-not-exist") is None

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            DocumentRepository(data_file=tmp_path / "missing.json")

    def test_unique_document_ids(self):
        repo = DocumentRepository()
        ids = [d.document_id for d in repo.all()]
        assert len(ids) == len(set(ids))

    def test_q3_figures_document_present(self):
        repo = DocumentRepository()
        ids = {d.document_id for d in repo.all()}
        assert "doc-q3-figures" in ids

    def test_unrelated_document_present(self):
        repo = DocumentRepository()
        ids = {d.document_id for d in repo.all()}
        # At least one non-financial document
        types = {d.document_type for d in repo.all()}
        assert len(types) > 1


# ---------------------------------------------------------------------------
# search_documents: no-filter
# ---------------------------------------------------------------------------

class TestSearchNoFilter:
    def test_no_filter_returns_all(self):
        result = _search()
        assert result["count"] == TOTAL_DOCUMENTS

    def test_count_matches_list_length(self):
        result = _search()
        assert result["count"] == len(result["documents"])

    def test_explicit_none_filters_returns_all(self):
        result = _search(query=None, document_type=None)
        assert result["count"] == TOTAL_DOCUMENTS


# ---------------------------------------------------------------------------
# search_documents: text query
# ---------------------------------------------------------------------------

class TestSearchTextQuery:
    def test_text_query_matches_content(self):
        result = _search(query="Q3 financial figures")
        assert result["count"] >= 1
        ids = {d["document_id"] for d in result["documents"]}
        assert "doc-q3-figures" in ids

    def test_text_query_matches_title(self):
        result = _search(query="Remote Work Policy")
        assert result["count"] >= 1

    def test_text_query_matches_filename(self):
        result = _search(query="Security_Audit_Checklist")
        assert result["count"] >= 1

    def test_text_query_case_insensitive_lower(self):
        lower = _search(query="q3 financial figures")
        mixed = _search(query="Q3 Financial Figures")
        assert lower["count"] == mixed["count"]

    def test_text_query_case_insensitive_upper(self):
        upper = _search(query="REMOTE WORK POLICY")
        lower = _search(query="remote work policy")
        assert upper["count"] == lower["count"]

    def test_no_match_returns_empty(self):
        result = _search(query="zzzz-nonexistent-9999")
        assert result["count"] == 0
        assert result["documents"] == []

    def test_q3_figures_matched_by_revenue(self):
        result = _search(query="Total revenue")
        ids = {d["document_id"] for d in result["documents"]}
        assert "doc-q3-figures" in ids

    def test_partial_word_match(self):
        result = _search(query="audit")
        assert result["count"] >= 1


# ---------------------------------------------------------------------------
# search_documents: document_type filter
# ---------------------------------------------------------------------------

class TestSearchDocumentType:
    def test_financial_type_returns_financial_docs(self):
        result = _search(document_type="financial")
        assert result["count"] >= 1
        for d in result["documents"]:
            assert d["document_type"] == "financial"

    def test_policy_type_returns_policy_docs(self):
        result = _search(document_type="policy")
        assert result["count"] >= 1
        for d in result["documents"]:
            assert d["document_type"] == "policy"

    def test_unknown_type_returns_empty(self):
        result = _search(document_type="nonexistent-type")
        assert result["count"] == 0

    def test_all_types_represented(self):
        all_types = {d["document_type"] for d in _search()["documents"]}
        assert "financial" in all_types


# ---------------------------------------------------------------------------
# search_documents: combined filters (AND semantics)
# ---------------------------------------------------------------------------

class TestSearchCombinedFilters:
    def test_query_and_type_combined(self):
        result = _search(query="Q3", document_type="financial")
        assert result["count"] >= 1
        for d in result["documents"]:
            assert d["document_type"] == "financial"

    def test_conflicting_query_and_type_returns_empty(self):
        # "Remote Work" is a policy document, not financial
        result = _search(query="Remote Work Policy", document_type="financial")
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# search_documents: result shape and content exclusion
# ---------------------------------------------------------------------------

class TestSearchResultShape:
    def test_result_is_valid_json(self):
        raw = search_documents()
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_result_has_count_and_documents_keys(self):
        result = _search()
        assert "count" in result
        assert "documents" in result

    def test_content_not_exposed_in_search_results(self):
        result = _search()
        for d in result["documents"]:
            assert "content" not in d, "content must not appear in search results"

    def test_each_entry_has_required_fields(self):
        result = _search()
        required = {"document_id", "filename", "title", "document_type",
                    "created_at", "updated_at"}
        for d in result["documents"]:
            assert required.issubset(d.keys())

    def test_timestamps_are_iso_strings(self):
        result = _search()
        for d in result["documents"]:
            datetime.fromisoformat(d["created_at"])
            datetime.fromisoformat(d["updated_at"])

    def test_result_round_trips_through_json(self):
        raw = search_documents()
        reparsed = json.loads(json.dumps(json.loads(raw)))
        assert reparsed["count"] == TOTAL_DOCUMENTS


# ---------------------------------------------------------------------------
# search_documents: deterministic ordering
# ---------------------------------------------------------------------------

class TestSearchOrdering:
    def test_ordered_by_created_at_ascending(self):
        result = _search()
        timestamps = [
            datetime.fromisoformat(d["created_at"])
            for d in result["documents"]
        ]
        assert timestamps == sorted(timestamps)

    def test_two_calls_return_identical_order(self):
        first = _search()["documents"]
        second = _search()["documents"]
        assert [d["document_id"] for d in first] == [
            d["document_id"] for d in second
        ]


# ---------------------------------------------------------------------------
# get_document
# ---------------------------------------------------------------------------

class TestGetDocument:
    def test_valid_id_returns_document(self):
        result = _get("doc-q3-figures")
        assert "error" not in result
        assert result["document_id"] == "doc-q3-figures"

    def test_result_includes_content(self):
        result = _get("doc-q3-figures")
        assert "content" in result
        assert len(result["content"]) > 0

    def test_content_contains_q3_figures(self):
        result = _get("doc-q3-figures")
        assert "42,700,000" in result["content"] or "42.7" in result["content"]

    def test_result_has_all_required_fields(self):
        result = _get("doc-q3-figures")
        for key in ("document_id", "filename", "title", "content",
                    "document_type", "created_at", "updated_at"):
            assert key in result

    def test_unknown_id_returns_error(self):
        result = _get("nonexistent-doc-id")
        assert "error" in result

    def test_unknown_id_error_mentions_id(self):
        result = _get("ghost-doc-999")
        assert "ghost-doc-999" in result["error"]

    def test_result_is_valid_json(self):
        raw = get_document(document_id="doc-q3-figures")
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    def test_result_round_trips_through_json(self):
        raw = get_document(document_id="doc-q3-figures")
        reparsed = json.loads(json.dumps(json.loads(raw)))
        assert reparsed["document_id"] == "doc-q3-figures"

    def test_different_documents_have_different_content(self):
        q3 = _get("doc-q3-figures")
        policy = _get("doc-remote-work-policy")
        assert q3["content"] != policy["content"]


# ---------------------------------------------------------------------------
# No mutation on read
# ---------------------------------------------------------------------------

class TestNoMutation:
    def test_search_does_not_change_repo_size(self):
        before = len(_repo)
        _search(query="Q3")
        assert len(_repo) == before

    def test_get_does_not_change_repo_size(self):
        before = len(_repo)
        _get("doc-q3-figures")
        assert len(_repo) == before

    def test_all_returns_independent_list(self):
        repo = DocumentRepository()
        snapshot = repo.all()
        original_len = len(repo)
        snapshot.clear()
        assert len(repo) == original_len