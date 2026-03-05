# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Structured contracts for KORDA chat/intake orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now_iso() -> str:
    """Return a UTC ISO timestamp."""
    return datetime.now(UTC).isoformat()


class ChatMode(StrEnum):
    """Supported orchestration modes."""

    AUTO = "auto"
    RAG_ONLY = "rag_only"
    TOOL_ONLY = "tool_only"
    RAG_PLUS_TOOL = "rag_plus_tool"


class ToolAdapterType(StrEnum):
    """How a tool should be invoked by the gateway."""

    MCP_STREAMABLE_HTTP = "mcp_streamable_http"
    MCP_STDIO = "mcp_stdio"
    HTTP_JSON = "http_json"


class IntakeSourceType(StrEnum):
    """Supported source classes for intake jobs."""

    DIRECT_UPLOAD = "direct_upload"
    FILESYSTEM = "filesystem"
    CONNECTOR_PULL = "connector_pull"
    S3 = "s3"
    SHAREPOINT = "sharepoint"
    EMAIL = "email"


class IntakeJobStatus(StrEnum):
    """Lifecycle states for intake jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class ToolCallStatus(StrEnum):
    """Execution status for tool calls."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class StartupState(StrEnum):
    """Startup bootstrap state for gateway readiness."""

    NOT_RUN = "not_run"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class ChatMessageV1(BaseModel):
    """Chat message unit."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]]


class ToolManifestV1(BaseModel):
    """Gateway-side tool registration contract."""

    schema_version: Literal["korda.tool_manifest.v1"] = "korda.tool_manifest.v1"
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2048)
    adapter_type: ToolAdapterType = ToolAdapterType.MCP_STREAMABLE_HTTP
    endpoint: str = Field(
        default="",
        description="Endpoint for adapter_type=http_json or streamable-http MCP server URL override.",
    )
    enabled: bool = True
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    max_output_bytes: int = Field(default=262_144, ge=1024, le=2_097_152)


class ToolCallRequestV1(BaseModel):
    """Request object for an individual tool call."""

    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = Field(default=None, max_length=128)


class ToolCallResultV1(BaseModel):
    """Result object for an individual tool call."""

    tool_name: str
    status: ToolCallStatus
    latency_ms: int = Field(ge=0)
    output: Any = None
    error: str | None = None


class IntakeProfileV1(BaseModel):
    """Profile used to standardize ingestion requests."""

    schema_version: Literal["korda.intake_profile.v1"] = "korda.intake_profile.v1"
    profile_id: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2048)
    split_options: dict[str, int] = Field(
        default_factory=lambda: {"chunk_size": 512, "chunk_overlap": 150}
    )
    generate_summary: bool = True
    required_metadata_fields: list[str] = Field(default_factory=list)
    allowed_extensions: list[str] = Field(default_factory=list)
    strict_threshold_overrides: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_split_options(self) -> "IntakeProfileV1":
        if "chunk_size" not in self.split_options or "chunk_overlap" not in self.split_options:
            raise ValueError("split_options must contain chunk_size and chunk_overlap")
        return self


class IntakeJobRequestV1(BaseModel):
    """Bulk intake request contract."""

    schema_version: Literal["korda.intake_job_request.v1"] = "korda.intake_job_request.v1"
    profile_id: str = Field(min_length=1, max_length=128)
    collection_name: str = Field(min_length=1, max_length=256)
    source_type: IntakeSourceType = IntakeSourceType.FILESYSTEM
    source_uri: str = Field(default="", max_length=2048)
    files: list[str] = Field(default_factory=list)
    blocking: bool = False
    custom_metadata: list[dict[str, Any]] = Field(default_factory=list)
    generate_summary_override: bool | None = None
    max_files: int = Field(default=500, ge=1, le=10_000)


class IntakeJobResultV1(BaseModel):
    """Bulk intake result contract."""

    schema_version: Literal["korda.intake_job_result.v1"] = "korda.intake_job_result.v1"
    job_id: str = Field(default_factory=lambda: uuid4().hex)
    status: IntakeJobStatus = IntakeJobStatus.QUEUED
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    request: IntakeJobRequestV1
    ingestor_task_ids: list[str] = Field(default_factory=list)
    processed_files: list[str] = Field(default_factory=list)
    failed_files: list[dict[str, Any]] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class ChatOrchestrationRequestV1(BaseModel):
    """Unified chat request contract for RAG + tool calls."""

    schema_version: Literal["korda.chat.request.v1"] = "korda.chat.request.v1"
    session_id: str | None = Field(default=None, max_length=128)
    mode: ChatMode = ChatMode.AUTO
    messages: list[ChatMessageV1] = Field(min_length=1, max_length=50000)
    collection_names: list[str] = Field(default_factory=list, max_length=5)
    use_knowledge_base: bool = True
    enable_citations: bool = True
    enable_reranker: bool | None = None
    requested_tools: list[ToolCallRequestV1] = Field(default_factory=list)
    rag_request_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_last_message(self) -> "ChatOrchestrationRequestV1":
        if self.messages[-1].role != "user":
            raise ValueError("The last message must have role='user'")
        return self


class ChatOrchestrationResponseV1(BaseModel):
    """Unified chat response contract."""

    schema_version: Literal["korda.chat.response.v1"] = "korda.chat.response.v1"
    session_id: str
    mode_resolved: ChatMode
    answer: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCallResultV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rag_response: dict[str, Any] | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class StartupStepResultV1(BaseModel):
    """Per-step startup bootstrap result."""

    step: str
    status: Literal["success", "failed", "skipped"]
    duration_ms: int = 0
    detail: str = ""


class StartupStatusV1(BaseModel):
    """Gateway startup/bootstrap status contract."""

    schema_version: Literal["korda.startup.status.v1"] = "korda.startup.status.v1"
    state: StartupState = StartupState.NOT_RUN
    run_reason: str = "startup"
    default_collection_name: str = ""
    default_collection_created: bool = False
    app_degraded: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = Field(default_factory=utc_now_iso)
    steps: list[StartupStepResultV1] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
