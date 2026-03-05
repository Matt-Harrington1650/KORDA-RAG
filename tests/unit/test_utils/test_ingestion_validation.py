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

"""Unit tests for strict ingestion validation contracts."""

import pytest

from nvidia_rag.utils.ingestion_validation import (
    parse_caption_record,
    parse_summary_record,
    summary_record_to_text,
    validate_caption_record,
    validate_summary_record,
)


def test_parse_caption_record_success():
    payload = {
        "schema_version": "korda.caption.v1",
        "artifact_type": "drawing",
        "discipline": "mechanical",
        "primary_subject": "Pump skid P-101",
        "document_number": "DOC-001",
        "entities": {
            "equipment_tags": ["P-101"],
            "instrument_tags": ["PT-101"],
            "line_numbers": ["10\"-P-1001-A1"],
            "drawing_numbers": ["DRW-001"],
            "revision_ids": ["A"],
            "specification_ids": ["SPEC-001"],
            "standard_references": ["ASME B31.3"],
        },
        "measurements": [],
        "quality": {"ocr_legibility": 0.92, "confidence": 0.93},
        "warnings": [],
    }

    record = parse_caption_record(payload)
    assert record.schema_version == "korda.caption.v1"
    assert record.entities.drawing_numbers == ["DRW-001"]


def test_parse_summary_record_invalid_json_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_summary_record("{this is not valid json}")


def test_validate_caption_record_fail_closed_missing_critical_identifiers():
    record = parse_caption_record(
        {
            "schema_version": "korda.caption.v1",
            "artifact_type": "drawing",
            "discipline": "piping",
            "primary_subject": "Piping layout",
            "document_number": None,
            "entities": {
                "equipment_tags": [],
                "instrument_tags": [],
                "line_numbers": [],
                "drawing_numbers": [],
                "revision_ids": [],
                "specification_ids": [],
                "standard_references": [],
            },
            "measurements": [],
            "quality": {"ocr_legibility": 0.9, "confidence": 0.95},
            "warnings": [],
        }
    )

    errors = validate_caption_record(record, min_confidence=0.8)
    assert any("missing both drawing_numbers and document_number" in e for e in errors)


def test_validate_summary_record_rejects_inferred_standard_values():
    record = parse_summary_record(
        {
            "schema_version": "korda.summary.v1",
            "document_identity": {
                "document_type": "drawing",
                "document_number": "DOC-100",
                "drawing_number": "DRW-100",
                "revision": "B",
                "title": "General arrangement",
                "issuer": "KORDA EPC",
                "approval_status": "Approved",
                "date_refs": ["2025-12-15"],
            },
            "executive_summary": "General arrangement drawing for package unit.",
            "technical_facts": ["Main equipment centerline established."],
            "constraints_and_assumptions": [],
            "risks_and_open_items": [],
            "codes_and_standards_verbatim": ["Inferred ASME B31.3"],
            "quality": {
                "confidence": 0.91,
                "missing_critical_fields": [],
                "ambiguities": [],
            },
        }
    )

    errors = validate_summary_record(record, min_confidence=0.85)
    assert any("codes_and_standards_verbatim" in e for e in errors)


def test_summary_record_to_text_renders_dual_layer_output():
    record = parse_summary_record(
        {
            "schema_version": "korda.summary.v1",
            "document_identity": {
                "document_type": "datasheet",
                "document_number": "DS-22",
                "drawing_number": None,
                "revision": "0",
                "title": "Pump datasheet",
                "issuer": "KORDA EPC",
                "approval_status": "For Review",
                "date_refs": ["2025-08-03"],
            },
            "executive_summary": "Pump datasheet with hydraulic and motor constraints.",
            "technical_facts": ["Rated flow 120 m3/h", "Differential head 85 m"],
            "constraints_and_assumptions": [],
            "risks_and_open_items": [],
            "codes_and_standards_verbatim": ["API 610"],
            "quality": {
                "confidence": 0.9,
                "missing_critical_fields": [],
                "ambiguities": [],
            },
        }
    )

    rendered = summary_record_to_text(record)
    assert "Pump datasheet with hydraulic and motor constraints." in rendered
    assert "Technical facts:" in rendered
