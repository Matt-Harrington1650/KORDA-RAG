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

"""Strict JSON contracts and fail-closed validation for ingestion pipelines."""

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

CRITICAL_ARTIFACT_TYPES = {"drawing", "pid", "datasheet"}
CRITICAL_DOCUMENT_TYPES = {"drawing", "pid", "datasheet"}

_INFERRED_MARKERS = (
    "inferred",
    "normalized",
    "approx",
    "assum",
    "guess",
    "estimated",
    "likely",
    "interpreted",
)
_INFERRED_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(marker) for marker in _INFERRED_MARKERS) + r")\b",
    re.IGNORECASE,
)


class CaptionEntities(BaseModel):
    """Extracted EPC entities from an image/caption artifact."""

    model_config = ConfigDict(extra="forbid")

    equipment_tags: list[str]
    instrument_tags: list[str]
    line_numbers: list[str]
    drawing_numbers: list[str]
    revision_ids: list[str]
    specification_ids: list[str]
    standard_references: list[str]


class CaptionMeasurement(BaseModel):
    """Structured measurement extracted from visual artifacts."""

    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | float | int | None
    unit: str | None
    context: str | None


class CaptionQuality(BaseModel):
    """Caption extraction quality indicators."""

    model_config = ConfigDict(extra="forbid")

    ocr_legibility: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class CaptionRecordV1(BaseModel):
    """Strict JSON schema for image caption extraction records."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["korda.caption.v1"]
    artifact_type: Literal[
        "drawing",
        "pid",
        "datasheet",
        "photo",
        "chart",
        "table",
        "diagram",
        "other",
        "unknown",
    ]
    discipline: Literal[
        "civil",
        "structural",
        "mechanical",
        "piping",
        "process",
        "electrical",
        "instrumentation",
        "controls",
        "hse",
        "procurement",
        "doc_control",
        "unknown",
    ]
    primary_subject: str
    document_number: str | None
    entities: CaptionEntities
    measurements: list[CaptionMeasurement]
    quality: CaptionQuality
    warnings: list[str]


class SummaryDocumentIdentity(BaseModel):
    """Document-control identity metadata for summaries."""

    model_config = ConfigDict(extra="forbid")

    document_type: str | None
    document_number: str | None
    drawing_number: str | None
    revision: str | None
    title: str | None
    issuer: str | None
    approval_status: str | None
    date_refs: list[str]


class SummaryQuality(BaseModel):
    """Summary extraction quality indicators."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(ge=0.0, le=1.0)
    missing_critical_fields: list[str]
    ambiguities: list[str]


class SummaryRecordV1(BaseModel):
    """Strict JSON schema for dual-layer document summaries."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["korda.summary.v1"]
    document_identity: SummaryDocumentIdentity
    executive_summary: str
    technical_facts: list[str]
    constraints_and_assumptions: list[str]
    risks_and_open_items: list[str]
    codes_and_standards_verbatim: list[str]
    quality: SummaryQuality


class MetadataRecordV1(BaseModel):
    """Strict JSON schema for mixed-EPC document-level enrichment."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["korda.metadata.v1"]
    project_id: str | None
    project_name: str | None
    discipline: str | None
    document_type: str | None
    document_number: str | None
    drawing_number: str | None
    revision: str | None
    revision_date: str | None
    asset_tag: str | None
    equipment_tag: str | None
    line_number: str | None
    instrument_tag: str | None
    specification_id: str | None
    vendor: str | None
    approval_status: str | None
    codes_standards: list[str]
    source_quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    extraction_warnings: list[str]


def _to_error_message(error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        loc = ".".join(str(v) for v in item.get("loc", [])) or "root"
        msg = item.get("msg", "invalid value")
        parts.append(f"{loc}: {msg}")
    return "; ".join(parts)


def _parse_json_object(payload: str | dict[str, Any], record_name: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if not isinstance(payload, str):
        raise ValueError(
            f"{record_name} payload must be a JSON object string, got {type(payload).__name__}"
        )

    stripped = payload.strip()
    if not stripped:
        raise ValueError(f"{record_name} payload is empty")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{record_name} payload is not valid JSON: {exc.msg}"
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"{record_name} payload must be a JSON object")
    return parsed


def _is_populated(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def _contains_inferred_standard(entries: list[str]) -> bool:
    return any(_INFERRED_PATTERN.search(value or "") for value in entries)


def _is_critical_document_type(document_type: str | None) -> bool:
    normalized = (document_type or "").lower().strip()
    if normalized in CRITICAL_DOCUMENT_TYPES:
        return True
    if "p&id" in normalized or "p and id" in normalized:
        return True
    return False


def parse_caption_record(payload: str | dict[str, Any]) -> CaptionRecordV1:
    """Parse and validate a caption payload using CaptionRecordV1."""
    data = _parse_json_object(payload, "CaptionRecordV1")
    try:
        return CaptionRecordV1.model_validate(data)
    except ValidationError as exc:
        raise ValueError(_to_error_message(exc)) from exc


def parse_summary_record(payload: str | dict[str, Any]) -> SummaryRecordV1:
    """Parse and validate a summary payload using SummaryRecordV1."""
    data = _parse_json_object(payload, "SummaryRecordV1")
    try:
        return SummaryRecordV1.model_validate(data)
    except ValidationError as exc:
        raise ValueError(_to_error_message(exc)) from exc


def parse_metadata_record(payload: str | dict[str, Any]) -> MetadataRecordV1:
    """Parse and validate a metadata enrichment payload using MetadataRecordV1."""
    data = _parse_json_object(payload, "MetadataRecordV1")
    try:
        return MetadataRecordV1.model_validate(data)
    except ValidationError as exc:
        raise ValueError(_to_error_message(exc)) from exc


def validate_caption_record(
    record: CaptionRecordV1,
    min_confidence: float,
    fail_on_missing_critical: bool = True,
) -> list[str]:
    """Apply deterministic fail-closed quality rules for caption records."""
    errors = []

    if record.artifact_type in CRITICAL_ARTIFACT_TYPES:
        if (
            len(record.entities.drawing_numbers) == 0
            and not _is_populated(record.document_number)
        ):
            errors.append(
                "critical artifact missing both drawing_numbers and document_number"
            )
        if record.quality.confidence < min_confidence:
            errors.append(
                f"caption confidence {record.quality.confidence:.3f} below minimum {min_confidence:.3f}"
            )

    if record.entities.standard_references and _contains_inferred_standard(
        record.entities.standard_references
    ):
        errors.append("standard_references contain inferred or normalized values")

    if fail_on_missing_critical and any(
        "missing critical" in warning.lower() for warning in record.warnings
    ):
        errors.append("warnings indicate missing critical fields")

    return errors


def validate_summary_record(
    record: SummaryRecordV1,
    min_confidence: float,
    fail_on_missing_critical: bool = True,
) -> list[str]:
    """Apply deterministic fail-closed quality rules for summary records."""
    errors = []

    critical_doc = _is_critical_document_type(record.document_identity.document_type)
    if critical_doc:
        if not _is_populated(record.document_identity.document_number) and not _is_populated(
            record.document_identity.drawing_number
        ):
            errors.append(
                "critical document missing both document_identity.document_number and document_identity.drawing_number"
            )
        if record.quality.confidence < min_confidence:
            errors.append(
                f"summary confidence {record.quality.confidence:.3f} below minimum {min_confidence:.3f}"
            )

    if record.codes_and_standards_verbatim and _contains_inferred_standard(
        record.codes_and_standards_verbatim
    ):
        errors.append("codes_and_standards_verbatim contain inferred or normalized values")

    if fail_on_missing_critical and record.quality.missing_critical_fields:
        errors.append(
            "quality.missing_critical_fields is non-empty: "
            + ", ".join(record.quality.missing_critical_fields)
        )

    return errors


def summary_record_to_text(record: SummaryRecordV1) -> str:
    """Render SummaryRecordV1 to a backward-compatible summary string."""
    executive = record.executive_summary.strip()
    technical_facts = [
        fact.strip() for fact in record.technical_facts if isinstance(fact, str) and fact.strip()
    ]
    if technical_facts:
        return f"{executive}\nTechnical facts: " + "; ".join(technical_facts)
    return executive


def record_to_canonical_json(record: BaseModel) -> str:
    """Serialize any contract record to stable canonical JSON."""
    return json.dumps(record.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
