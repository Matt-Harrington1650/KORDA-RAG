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

"""Tests for strict caption validation hooks in ingestor pipeline."""

from types import SimpleNamespace

from nvidia_rag.ingestor_server.main import NvidiaRAGIngestor


def _build_ingestor_stub(
    strict_mode: bool = True,
    fail_on_missing_critical: bool = True,
    per_artifact_thresholds: dict | None = None,
) -> NvidiaRAGIngestor:
    ingestor = object.__new__(NvidiaRAGIngestor)
    ingestor.config = SimpleNamespace(
        ingestion_json_strict_mode=strict_mode,
        ingestion_caption_min_confidence=0.8,
        ingestion_caption_min_confidence_by_artifact=per_artifact_thresholds or {},
        ingestion_fail_on_missing_critical=fail_on_missing_critical,
    )
    ingestor.metrics_client = None
    return ingestor


def _valid_caption_payload() -> str:
    return """{
      "schema_version":"korda.caption.v1",
      "artifact_type":"drawing",
      "discipline":"piping",
      "primary_subject":"Piping isometric",
      "document_number":"DOC-1",
      "entities":{
        "equipment_tags":["P-101"],
        "instrument_tags":["PT-101"],
        "line_numbers":["L-1001"],
        "drawing_numbers":["DRW-1"],
        "revision_ids":["A"],
        "specification_ids":["SPEC-1"],
        "standard_references":["ASME B31.3"]
      },
      "measurements":[],
      "quality":{"ocr_legibility":0.90,"confidence":0.92},
      "warnings":[]
    }"""


def test_validate_caption_records_skips_when_strict_mode_disabled():
    ingestor = _build_ingestor_stub(strict_mode=False)
    results = []
    filepaths = []

    validation_errors, failures = ingestor._validate_caption_records(results, filepaths)
    assert validation_errors == []
    assert failures == []


def test_validate_caption_records_accepts_valid_caption_json():
    ingestor = _build_ingestor_stub(strict_mode=True)
    results = [
        [
            {
                "document_type": "image",
                "metadata": {
                    "source_metadata": {"source_id": "/tmp/doc1.pdf"},
                    "content_metadata": {"page_number": 1},
                    "image_metadata": {"caption": _valid_caption_payload()},
                },
            }
        ]
    ]
    filepaths = ["/tmp/doc1.pdf"]

    validation_errors, failures = ingestor._validate_caption_records(results, filepaths)
    assert validation_errors == []
    assert failures == []


def test_validate_caption_records_fail_closed_for_invalid_json():
    ingestor = _build_ingestor_stub(strict_mode=True, fail_on_missing_critical=True)
    results = [
        [
            {
                "document_type": "image",
                "metadata": {
                    "source_metadata": {"source_id": "/tmp/doc2.pdf"},
                    "content_metadata": {"page_number": 2},
                    "image_metadata": {"caption": "{invalid json"},
                },
            }
        ]
    ]
    filepaths = ["/tmp/doc2.pdf"]

    validation_errors, failures = ingestor._validate_caption_records(results, filepaths)
    assert len(validation_errors) == 1
    assert validation_errors[0]["code"] == "CAPTION_SCHEMA_VALIDATION_FAILED"
    assert len(failures) == 1
    assert "doc2.pdf" in str(failures[0][0])


def test_validate_caption_records_warn_only_when_fail_closed_disabled():
    ingestor = _build_ingestor_stub(strict_mode=True, fail_on_missing_critical=False)
    results = [
        [
            {
                "document_type": "image",
                "metadata": {
                    "source_metadata": {"source_id": "/tmp/doc3.pdf"},
                    "content_metadata": {"page_number": 3},
                    "image_metadata": {"caption": "{invalid json"},
                },
            }
        ]
    ]
    filepaths = ["/tmp/doc3.pdf"]

    validation_errors, failures = ingestor._validate_caption_records(results, filepaths)
    assert len(validation_errors) == 1
    assert failures == []


def test_validate_caption_records_uses_per_artifact_threshold_override():
    ingestor = _build_ingestor_stub(
        strict_mode=True,
        fail_on_missing_critical=True,
        per_artifact_thresholds={"drawing": 0.95},
    )
    results = [
        [
            {
                "document_type": "image",
                "metadata": {
                    "source_metadata": {"source_id": "/tmp/doc4.pdf"},
                    "content_metadata": {"page_number": 1},
                    "image_metadata": {"caption": _valid_caption_payload()},
                },
            }
        ]
    ]
    filepaths = ["/tmp/doc4.pdf"]

    validation_errors, failures = ingestor._validate_caption_records(results, filepaths)
    assert len(validation_errors) == 1
    assert validation_errors[0]["code"] == "CAPTION_SCHEMA_VALIDATION_FAILED"
    assert len(failures) == 1
