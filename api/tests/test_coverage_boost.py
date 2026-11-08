"""Additional unit tests to cover hosted provider, chroma retriever, and health routes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.providers.llm.hosted import HostedProvider
from app.retrieval.chroma import ChromaRetriever
from app.schemas import Passage


def test_hosted_provider_build_messages() -> None:
    settings = Settings(llm_api_key="test-key", hosted_base_url="https://api.test.com")
    provider = HostedProvider(settings)
    passages = [
        Passage(
            chunk_id="c1",
            text="Evidence test",
            source="rules.pdf",
            section="1.0",
            page=1,
            score=0.9,
        )
    ]
    msgs = provider._build_messages("What is test?", passages)
    assert len(msgs) == 2
    assert "Evidence test" in msgs[1]["content"]


def test_hosted_provider_generate_success() -> None:
    settings = Settings(llm_api_key="test-key", hosted_base_url="https://api.test.com")
    provider = HostedProvider(settings)
    passages = [
        Passage(
            chunk_id="c1",
            text="Evidence test",
            source="rules.pdf",
            section="1.0",
            page=1,
            score=0.9,
        )
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "answer": "This is a test answer.",
                            "reasoning": "Valid context found.",
                            "citations": [{"source": "rules.pdf", "section": "1.0", "page": 1}],
                            "answered_from_context": True,
                            "confidence": "high",
                        }
                    )
                }
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_resp):
        ans = provider.generate("Test question", passages)
        assert ans.answered_from_context is True
        assert len(ans.citations) == 1
        assert ans.confidence == "high"


def test_chroma_retriever_empty() -> None:
    settings = Settings(chroma_host="chroma", chroma_port=8000)
    fake_client = MagicMock()
    fake_collection = MagicMock()
    fake_collection.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }
    fake_client.get_collection.return_value = fake_collection

    with patch("chromadb.HttpClient", return_value=fake_client):
        retriever = ChromaRetriever(settings)
        retriever._embed_query = lambda q: [0.0] * 384  # type: ignore[method-assign]
        results = retriever.retrieve("Any question", k=3)
        assert results == []
