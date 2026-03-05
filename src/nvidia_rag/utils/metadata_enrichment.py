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

"""Post-ingestion metadata enrichment utilities."""

import asyncio
import os
import time
from typing import Any

from langchain_core.output_parsers.string import StrOutputParser
from langchain_core.prompts.chat import ChatPromptTemplate

from nvidia_rag.utils.configuration import NvidiaRAGConfig
from nvidia_rag.utils.ingestion_validation import (
    MetadataRecordV1,
    parse_caption_record,
    parse_metadata_record,
    record_to_canonical_json,
)
from nvidia_rag.utils.llm import get_llm

import logging

logger = logging.getLogger(__name__)

_CRITICAL_METADATA_DOC_TYPES = {"drawing", "pid", "datasheet"}


def _normalize_doc_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if "p&id" in normalized or "p and id" in normalized:
        return "pid"
    return normalized


def _is_populated(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def _extract_caption_text(caption_payload: Any) -> str:
    """Best-effort conversion of structured caption payload to flat text."""
    if not caption_payload:
        return ""

    if isinstance(caption_payload, dict):
        try:
            caption_record = parse_caption_record(caption_payload)
            return (
                f"artifact_type={caption_record.artifact_type}; "
                f"discipline={caption_record.discipline}; "
                f"primary_subject={caption_record.primary_subject}; "
                f"document_number={caption_record.document_number or ''}; "
                f"drawing_numbers={','.join(caption_record.entities.drawing_numbers)}; "
                f"standard_references={','.join(caption_record.entities.standard_references)}"
            )
        except Exception:
            return str(caption_payload)

    if isinstance(caption_payload, str):
        stripped = caption_payload.strip()
        if not stripped:
            return ""
        try:
            caption_record = parse_caption_record(stripped)
            return (
                f"artifact_type={caption_record.artifact_type}; "
                f"discipline={caption_record.discipline}; "
                f"primary_subject={caption_record.primary_subject}; "
                f"document_number={caption_record.document_number or ''}; "
                f"drawing_numbers={','.join(caption_record.entities.drawing_numbers)}; "
                f"standard_references={','.join(caption_record.entities.standard_references)}"
            )
        except Exception:
            return stripped

    return str(caption_payload)


def _extract_content_from_element(element: dict[str, Any]) -> str | None:
    doc_type = element.get("document_type")
    metadata = element.get("metadata", {})

    if doc_type == "text":
        content = metadata.get("content")
        return content if isinstance(content, str) else None

    if doc_type == "structured":
        table_content = metadata.get("table_metadata", {}).get("table_content")
        return table_content if isinstance(table_content, str) else None

    if doc_type == "image":
        caption_payload = metadata.get("image_metadata", {}).get("caption")
        caption_text = _extract_caption_text(caption_payload)
        return caption_text if caption_text else None

    if doc_type == "audio":
        transcript = metadata.get("audio_metadata", {}).get("audio_transcript")
        return transcript if isinstance(transcript, str) else None

    return None


def _build_document_text(
    result_elements: list[dict[str, Any]],
    max_input_chars: int,
) -> str:
    parts: list[str] = []
    for element in result_elements:
        text = _extract_content_from_element(element)
        if text:
            parts.append(text.strip())

    merged = "\n\n".join(part for part in parts if part)
    if len(merged) > max_input_chars:
        return merged[:max_input_chars]
    return merged


def _validate_metadata_record(
    record: MetadataRecordV1,
    min_source_quality_score: float,
    fail_on_missing_critical: bool,
) -> list[str]:
    errors: list[str] = []

    normalized_doc_type = _normalize_doc_type(record.document_type)
    if normalized_doc_type in _CRITICAL_METADATA_DOC_TYPES:
        if not _is_populated(record.document_number) and not _is_populated(
            record.drawing_number
        ):
            errors.append(
                "critical metadata missing both document_number and drawing_number"
            )

    if (
        record.source_quality_score is not None
        and record.source_quality_score < min_source_quality_score
    ):
        errors.append(
            "source_quality_score "
            f"{record.source_quality_score:.3f} below minimum {min_source_quality_score:.3f}"
        )

    if fail_on_missing_critical and any(
        "missing critical" in warning.lower()
        for warning in record.extraction_warnings
        if isinstance(warning, str)
    ):
        errors.append("metadata extraction warnings indicate missing critical fields")

    return errors


def _get_metadata_llm(config: NvidiaRAGConfig):
    llm_kwargs: dict[str, Any] = {
        "config": config,
        "model": config.metadata.extraction_model_name,
        "temperature": config.metadata.extraction_temperature,
        "top_p": config.metadata.extraction_top_p,
        "api_key": config.metadata.get_api_key(),
    }
    if config.metadata.extraction_server_url:
        llm_kwargs["llm_endpoint"] = config.metadata.extraction_server_url
    return get_llm(**llm_kwargs)


def _get_file_name(result_elements: list[dict[str, Any]]) -> str:
    if not result_elements:
        return "unknown"
    source_id = (
        result_elements[0].get("metadata", {}).get("source_metadata", {}).get("source_id")
    )
    if not source_id:
        return "unknown"
    return os.path.basename(source_id)


async def extract_post_ingest_metadata(
    results: list[list[dict[str, Any]]],
    filepaths: list[str],
    collection_name: str,
    config: NvidiaRAGConfig,
    prompts: dict[str, Any],
    metrics_client: Any = None,
) -> dict[str, Any]:
    """Extract strict metadata records for ingested documents."""
    if not config.metadata.enable_post_ingest_enrichment:
        return {
            "records_by_filename": {},
            "validation_errors": [],
            "failures": [],
        }

    prompt_config = prompts.get("metadata_extraction_prompt")
    if not prompt_config:
        return {
            "records_by_filename": {},
            "validation_errors": [
                {
                    "code": "METADATA_PROMPT_MISSING",
                    "message": "metadata_extraction_prompt not found in prompt configuration",
                    "metadata": {"collection_name": collection_name},
                }
            ],
            "failures": [],
        }

    llm = _get_metadata_llm(config)
    chain = (
        ChatPromptTemplate.from_messages(
            [
                ("system", prompt_config["system"]),
                ("human", prompt_config["human"]),
            ]
        )
        | llm
        | StrOutputParser()
    )

    file_lookup = {os.path.basename(path): path for path in filepaths}
    semaphore = asyncio.Semaphore(max(1, int(config.metadata.max_parallelization)))
    records_by_filename: dict[str, dict[str, Any]] = {}
    validation_errors: list[dict[str, Any]] = []
    failures: list[tuple[str, Exception]] = []

    async def _process_single_document(result_elements: list[dict[str, Any]]) -> None:
        if not result_elements:
            return

        file_name = _get_file_name(result_elements)
        file_path = file_lookup.get(file_name, file_name)
        start_time = time.time()

        async with semaphore:
            try:
                document_text = _build_document_text(
                    result_elements=result_elements,
                    max_input_chars=config.metadata.max_input_chars,
                )
                if not document_text:
                    raise ValueError("no extracted content available for metadata enrichment")

                raw_response = await chain.ainvoke(
                    {"document_text": document_text},
                    config={"run_name": f"metadata-enrichment-{file_name}"},
                )
                metadata_record = parse_metadata_record(raw_response)
                rule_errors = _validate_metadata_record(
                    metadata_record,
                    min_source_quality_score=config.metadata.min_source_quality_score,
                    fail_on_missing_critical=config.ingestion_fail_on_missing_critical,
                )
                if rule_errors:
                    raise ValueError("; ".join(rule_errors))

                records_by_filename[file_name] = {
                    "record": metadata_record.model_dump(mode="json"),
                    "json": record_to_canonical_json(metadata_record),
                }

                if metrics_client is not None:
                    metrics_client.update_metadata_enrichment_job(
                        status="success",
                        duration_ms=(time.time() - start_time) * 1000.0,
                        document_class=_normalize_doc_type(metadata_record.document_type)
                        or "unknown",
                    )
                    metrics_client.update_strict_validation_record(
                        phase="metadata",
                        outcome="success",
                        error_code="NONE",
                        document_class=_normalize_doc_type(metadata_record.document_type)
                        or "unknown",
                    )

            except Exception as exc:
                error_text = str(exc)
                validation_errors.append(
                    {
                        "code": "METADATA_SCHEMA_VALIDATION_FAILED",
                        "message": "MetadataRecordV1 validation failed",
                        "metadata": {
                            "filename": file_name,
                            "collection_name": collection_name,
                            "error": error_text,
                        },
                    }
                )
                if config.ingestion_json_strict_mode and config.ingestion_fail_on_missing_critical:
                    failures.append(
                        (
                            file_path,
                            ValueError(f"Metadata enrichment failed: {error_text}"),
                        )
                    )

                if metrics_client is not None:
                    metrics_client.update_metadata_enrichment_job(
                        status="failure",
                        duration_ms=(time.time() - start_time) * 1000.0,
                        document_class="unknown",
                    )
                    metrics_client.update_strict_validation_record(
                        phase="metadata",
                        outcome="failure",
                        error_code="METADATA_SCHEMA_VALIDATION_FAILED",
                        document_class="unknown",
                    )

    await asyncio.gather(
        *[_process_single_document(result_list) for result_list in results],
        return_exceptions=False,
    )

    return {
        "records_by_filename": records_by_filename,
        "validation_errors": validation_errors,
        "failures": failures,
    }
