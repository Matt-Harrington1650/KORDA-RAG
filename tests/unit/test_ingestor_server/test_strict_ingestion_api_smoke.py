# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""API smoke tests for strict ingestion fixture behavior."""

import json
import os
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from nvidia_rag.ingestor_server.server import app
from nvidia_rag.utils.ingestion_validation import (
    parse_caption_record,
    parse_summary_record,
    validate_caption_record,
    validate_summary_record,
)


def _valid_caption_fixture() -> str:
    return """{
      "schema_version":"korda.caption.v1",
      "artifact_type":"drawing",
      "discipline":"piping",
      "primary_subject":"P&ID fragment",
      "document_number":"DOC-200",
      "entities":{
        "equipment_tags":["P-200"],
        "instrument_tags":["PT-200"],
        "line_numbers":["L-2001"],
        "drawing_numbers":["DRW-200"],
        "revision_ids":["B"],
        "specification_ids":["SPEC-200"],
        "standard_references":["ASME B31.3"]
      },
      "measurements":[],
      "quality":{"ocr_legibility":0.95,"confidence":0.92},
      "warnings":[]
    }"""


def _valid_summary_fixture() -> str:
    return """{
      "schema_version":"korda.summary.v1",
      "document_identity":{
        "document_type":"drawing",
        "document_number":"DOC-200",
        "drawing_number":"DRW-200",
        "revision":"B",
        "title":"P&ID Area 200",
        "issuer":"KORDA EPC",
        "approval_status":"Approved",
        "date_refs":["2025-12-01"]
      },
      "executive_summary":"P&ID drawing defines process line routing and instrumentation for Area 200.",
      "technical_facts":["Main process line L-2001 connects separator to heater."],
      "constraints_and_assumptions":[],
      "risks_and_open_items":[],
      "codes_and_standards_verbatim":["ASME B31.3"],
      "quality":{"confidence":0.91,"missing_critical_fields":[],"ambiguities":[]}
    }"""


def _invalid_summary_fixture() -> str:
    return """{
      "schema_version":"korda.summary.v1",
      "document_identity":{
        "document_type":"drawing",
        "document_number":null,
        "drawing_number":null,
        "revision":"B",
        "title":"P&ID Area 200",
        "issuer":"KORDA EPC",
        "approval_status":"Approved",
        "date_refs":["2025-12-01"]
      },
      "executive_summary":"P&ID drawing for Area 200.",
      "technical_facts":[],
      "constraints_and_assumptions":[],
      "risks_and_open_items":[],
      "codes_and_standards_verbatim":["ASME B31.3"],
      "quality":{"confidence":0.91,"missing_critical_fields":["document_number"],"ambiguities":[]}
    }"""


def _build_upload_request_payload(blocking: bool = True) -> dict:
    return {
        "collection_name": "strict_ingestion_smoke",
        "blocking": blocking,
        "split_options": {"chunk_size": 512, "chunk_overlap": 150},
        "custom_metadata": [],
        "generate_summary": True,
        "summary_options": {"summarization_strategy": "single"},
    }


def test_post_documents_strict_fixtures_surface_validation_and_failures():
    """POST /documents should surface strict fixture failures via canonical response fields."""

    async def _upload_documents(**kwargs):
        filename = os.path.basename(kwargs["filepaths"][0])
        validation_errors = []
        failed_documents = []

        # Caption fixture intentionally malformed.
        try:
            _ = parse_caption_record("{invalid json")
        except Exception as exc:
            validation_errors.append(
                {
                    "code": "CAPTION_SCHEMA_VALIDATION_FAILED",
                    "message": "CaptionRecordV1 validation failed",
                    "metadata": {"filename": filename, "error": str(exc)},
                }
            )
            failed_documents.append(
                {
                    "document_name": filename,
                    "error_message": f"Caption strict validation failed: {exc}",
                }
            )

        # Summary fixture intentionally fails critical rules.
        try:
            summary_record = parse_summary_record(_invalid_summary_fixture())
            summary_rule_errors = validate_summary_record(summary_record, min_confidence=0.85)
            if summary_rule_errors:
                raise ValueError("; ".join(summary_rule_errors))
        except Exception as exc:
            validation_errors.append(
                {
                    "code": "SUMMARY_SCHEMA_VALIDATION_FAILED",
                    "message": "SummaryRecordV1 validation failed",
                    "metadata": {"filename": filename, "error": str(exc)},
                }
            )
            failed_documents.append(
                {
                    "document_name": filename,
                    "error_message": f"Summary strict validation failed: {exc}",
                }
            )

        return {
            "message": "Document upload job successfully completed.",
            "total_documents": 1,
            "documents": [],
            "failed_documents": failed_documents,
            "validation_errors": validation_errors,
        }

    mock_ingestor = SimpleNamespace(upload_documents=AsyncMock(side_effect=_upload_documents))

    with patch("nvidia_rag.ingestor_server.server.NV_INGEST_INGESTOR", mock_ingestor):
        client = TestClient(app)
        files = {"documents": ("strict-fixture.txt", BytesIO(b"fixture"), "text/plain")}
        payload = _build_upload_request_payload(blocking=True)
        response = client.post("/v1/documents", files=files, data={"data": json.dumps(payload)})

    assert response.status_code == 200
    body = response.json()
    assert len(body["validation_errors"]) >= 2
    assert any(err["code"] == "CAPTION_SCHEMA_VALIDATION_FAILED" for err in body["validation_errors"])
    assert any(err["code"] == "SUMMARY_SCHEMA_VALIDATION_FAILED" for err in body["validation_errors"])
    assert len(body["failed_documents"]) >= 1


def test_post_documents_strict_valid_fixtures_return_clean_response():
    """POST /documents with valid strict fixtures should return no failures."""

    async def _upload_documents(**kwargs):
        filename = os.path.basename(kwargs["filepaths"][0])
        validation_errors = []

        caption_record = parse_caption_record(_valid_caption_fixture())
        validation_errors.extend(
            {
                "code": "CAPTION_RULE_FAILED",
                "message": message,
                "metadata": {"filename": filename},
            }
            for message in validate_caption_record(caption_record, min_confidence=0.8)
        )

        summary_record = parse_summary_record(_valid_summary_fixture())
        validation_errors.extend(
            {
                "code": "SUMMARY_RULE_FAILED",
                "message": message,
                "metadata": {"filename": filename},
            }
            for message in validate_summary_record(summary_record, min_confidence=0.85)
        )

        return {
            "message": "Document upload job successfully completed.",
            "total_documents": 1,
            "documents": [
                {
                    "document_name": filename,
                    "metadata": {"filename": filename},
                    "document_info": {},
                }
            ],
            "failed_documents": [],
            "validation_errors": validation_errors,
        }

    mock_ingestor = SimpleNamespace(upload_documents=AsyncMock(side_effect=_upload_documents))

    with patch("nvidia_rag.ingestor_server.server.NV_INGEST_INGESTOR", mock_ingestor):
        client = TestClient(app)
        files = {"documents": ("strict-fixture.txt", BytesIO(b"fixture"), "text/plain")}
        payload = _build_upload_request_payload(blocking=True)
        response = client.post("/v1/documents", files=files, data={"data": json.dumps(payload)})

    assert response.status_code == 200
    body = response.json()
    assert body["validation_errors"] == []
    assert body["failed_documents"] == []
    assert len(body["documents"]) == 1
