# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""FastAPI server for KORDA chat and intake orchestration."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from nvidia_rag.chat_gateway.models import (
    ChatOrchestrationRequestV1,
    ChatOrchestrationResponseV1,
    IntakeJobRequestV1,
    IntakeJobResultV1,
    StartupStatusV1,
)
from nvidia_rag.chat_gateway.service import GatewayService, GatewaySettings

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())
logger = logging.getLogger(__name__)

SETTINGS = GatewaySettings.from_env()
SERVICE = GatewayService(SETTINGS)

tags_metadata = [
    {
        "name": "Health APIs",
        "description": "APIs for liveliness and dependency checks.",
    },
    {
        "name": "Chat APIs",
        "description": "Unified chat orchestration APIs for RAG and tools.",
    },
    {
        "name": "Intake APIs",
        "description": "Data intake APIs for upload and connector-style bulk ingestion.",
    },
]

app = FastAPI(
    title="KORDA Chat Gateway",
    description="Gateway for KORDA chat orchestration and easy ingestion entrypoints.",
    version="1.0.0",
    openapi_tags=tags_metadata,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    if SETTINGS.auto_startup_bootstrap:
        try:
            await SERVICE.run_startup_bootstrap(run_reason="startup")
        except Exception as exc:
            logger.exception("Gateway startup bootstrap failed: %s", exc)


class IntakeUploadFormPayload(BaseModel):
    """Structured JSON payload for /v1/intake/upload multipart endpoint."""

    profile_id: str = Field(..., description="Intake profile identifier")
    collection_name: str = Field(..., description="Target collection name")
    blocking: bool = Field(default=False, description="Run ingestion in blocking mode")
    custom_metadata: list[dict[str, Any]] = Field(default_factory=list)
    generate_summary_override: bool | None = None


@app.get("/v1/health", tags=["Health APIs"])
async def health() -> dict[str, Any]:
    """Gateway health endpoint."""
    startup = await SERVICE.get_startup_status()
    return {
        "message": "KORDA chat gateway is up.",
        "rag_base_url": SETTINGS.rag_base_url,
        "ingestor_base_url": SETTINGS.ingestor_base_url,
        "tool_count": len(SERVICE.tools.list_tools()),
        "profile_count": len(SERVICE.intake_profiles),
        "startup_state": startup.state,
        "app_degraded": startup.app_degraded,
    }


@app.get("/v1/startup/status", response_model=StartupStatusV1, tags=["Health APIs"])
async def startup_status() -> StartupStatusV1:
    """Return latest startup/bootstrap status."""
    return await SERVICE.get_startup_status()


@app.post("/v1/startup/run", response_model=StartupStatusV1, tags=["Health APIs"])
async def startup_run() -> StartupStatusV1:
    """Manually rerun startup bootstrap checks and collection ensure-create."""
    return await SERVICE.run_startup_bootstrap(run_reason="manual")


@app.get("/v1/tools", tags=["Chat APIs"])
async def list_tools() -> dict[str, Any]:
    """List enabled tool manifests."""
    return {
        "tools": [tool.model_dump() for tool in SERVICE.tools.list_tools()],
    }


@app.get("/v1/intake/profiles", tags=["Intake APIs"])
async def list_intake_profiles() -> dict[str, Any]:
    """List configured intake profiles."""
    return {
        "profiles": [profile.model_dump() for profile in SERVICE.intake_profiles.values()],
    }


@app.post("/v1/chat", response_model=ChatOrchestrationResponseV1, tags=["Chat APIs"])
async def orchestrate_chat(request: ChatOrchestrationRequestV1) -> ChatOrchestrationResponseV1:
    """Run chat orchestration with optional tool calls and RAG retrieval/generation."""
    return await SERVICE.orchestrate_chat(request)


@app.get("/v1/chat/sessions/{session_id}", tags=["Chat APIs"])
async def get_chat_session(session_id: str) -> dict[str, Any]:
    """Return session event history captured by the gateway."""
    events = await SERVICE.store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {"session_id": session_id, "events": events}


@app.post("/v1/intake/upload", tags=["Intake APIs"])
async def intake_upload(
    data: str = Form(..., description="JSON payload matching IntakeUploadFormPayload"),
    documents: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """User-friendly upload endpoint that applies an intake profile and forwards to ingestor."""
    try:
        parsed = IntakeUploadFormPayload(**json.loads(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid intake payload JSON: {exc}") from exc

    return await SERVICE.intake_upload(
        profile_id=parsed.profile_id,
        collection_name=parsed.collection_name,
        files=documents,
        blocking=parsed.blocking,
        custom_metadata=parsed.custom_metadata,
        generate_summary_override=parsed.generate_summary_override,
    )


@app.post("/v1/intake/bulk", response_model=IntakeJobResultV1, tags=["Intake APIs"])
async def submit_intake_bulk_job(request: IntakeJobRequestV1) -> IntakeJobResultV1:
    """Submit a bulk intake job for connector/filesystem sources."""
    return await SERVICE.submit_bulk_job(request)


@app.get("/v1/intake/jobs/{job_id}", response_model=IntakeJobResultV1, tags=["Intake APIs"])
async def get_intake_bulk_job(job_id: str) -> IntakeJobResultV1:
    """Get bulk intake job status."""
    job = await SERVICE.store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Intake job '{job_id}' not found")
    return job


@app.get("/v1/configuration", tags=["Health APIs"])
async def get_configuration() -> dict[str, Any]:
    """Expose runtime configuration without secrets."""
    return {
        "rag_base_url": SETTINGS.rag_base_url,
        "ingestor_base_url": SETTINGS.ingestor_base_url,
        "milvus_endpoint": SETTINGS.milvus_endpoint,
        "mcp_url": SETTINGS.mcp_url,
        "mcp_transport": SETTINGS.mcp_transport,
        "request_timeout_seconds": SETTINGS.request_timeout_seconds,
        "tool_timeout_seconds": SETTINGS.tool_timeout_seconds,
        "max_tool_output_bytes": SETTINGS.max_tool_output_bytes,
        "intake_profiles_file": SETTINGS.intake_profiles_file,
        "tool_manifest_file": SETTINGS.tool_manifest_file,
        "metadata_schema_file": SETTINGS.metadata_schema_file,
        "default_collection_name": SETTINGS.default_collection_name,
        "store_backend": SETTINGS.store_backend,
        "redis_host": SETTINGS.redis_host,
        "redis_port": SETTINGS.redis_port,
        "redis_db": SETTINGS.redis_db,
        "intake_profiles_file_exists": Path(SETTINGS.intake_profiles_file).exists(),
        "tool_manifest_file_exists": Path(SETTINGS.tool_manifest_file).exists(),
        "metadata_schema_file_exists": Path(SETTINGS.metadata_schema_file).exists(),
    }
