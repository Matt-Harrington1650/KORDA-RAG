# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from langchain_core.runnables import RunnableLambda

from nvidia_rag.utils.configuration import NvidiaRAGConfig
from nvidia_rag.utils.metadata_enrichment import extract_post_ingest_metadata


def _sample_results():
    return [
        [
            {
                "document_type": "text",
                "metadata": {
                    "source_metadata": {"source_id": "/tmp/doc-a.pdf"},
                    "content": "P&ID drawing DOC-100 references ASME B31.3",
                    "content_metadata": {"page_number": 1},
                },
            }
        ]
    ]


def _prompts():
    return {
        "metadata_extraction_prompt": {
            "system": "Return strict JSON only.",
            "human": "Source text:\n{document_text}",
        }
    }


@pytest.mark.asyncio
async def test_metadata_enrichment_disabled_returns_empty():
    config = NvidiaRAGConfig(metadata={"enable_post_ingest_enrichment": False})
    result = await extract_post_ingest_metadata(
        results=_sample_results(),
        filepaths=["/tmp/doc-a.pdf"],
        collection_name="demo",
        config=config,
        prompts=_prompts(),
    )
    assert result["records_by_filename"] == {}
    assert result["validation_errors"] == []
    assert result["failures"] == []


@pytest.mark.asyncio
async def test_metadata_enrichment_success(monkeypatch):
    config = NvidiaRAGConfig(
        metadata={"enable_post_ingest_enrichment": True, "max_parallelization": 1},
        ingestion_json_strict_mode=True,
        ingestion_fail_on_missing_critical=True,
    )
    response_json = """{
      "schema_version": "korda.metadata.v1",
      "project_id": "P-1",
      "project_name": "Korda Pilot",
      "discipline": "piping",
      "document_type": "drawing",
      "document_number": "DOC-100",
      "drawing_number": "DRW-100",
      "revision": "A",
      "revision_date": "2025-12-15",
      "asset_tag": null,
      "equipment_tag": "P-100",
      "line_number": "L-100",
      "instrument_tag": null,
      "specification_id": "SPEC-100",
      "vendor": null,
      "approval_status": "Approved",
      "codes_standards": ["ASME B31.3"],
      "source_quality_score": 0.91,
      "extraction_warnings": []
    }"""
    monkeypatch.setattr(
        "nvidia_rag.utils.metadata_enrichment.get_llm",
        lambda **kwargs: RunnableLambda(lambda _: response_json),
    )

    result = await extract_post_ingest_metadata(
        results=_sample_results(),
        filepaths=["/tmp/doc-a.pdf"],
        collection_name="demo",
        config=config,
        prompts=_prompts(),
    )

    assert "doc-a.pdf" in result["records_by_filename"]
    assert result["validation_errors"] == []
    assert result["failures"] == []


@pytest.mark.asyncio
async def test_metadata_enrichment_fail_closed(monkeypatch):
    config = NvidiaRAGConfig(
        metadata={"enable_post_ingest_enrichment": True, "max_parallelization": 1},
        ingestion_json_strict_mode=True,
        ingestion_fail_on_missing_critical=True,
    )
    monkeypatch.setattr(
        "nvidia_rag.utils.metadata_enrichment.get_llm",
        lambda **kwargs: RunnableLambda(lambda _: "{invalid json"),
    )

    result = await extract_post_ingest_metadata(
        results=_sample_results(),
        filepaths=["/tmp/doc-a.pdf"],
        collection_name="demo",
        config=config,
        prompts=_prompts(),
    )

    assert len(result["validation_errors"]) == 1
    assert result["validation_errors"][0]["code"] == "METADATA_SCHEMA_VALIDATION_FAILED"
    assert len(result["failures"]) == 1
