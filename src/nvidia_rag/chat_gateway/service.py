# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Business logic for KORDA chat and intake orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx
import yaml
from fastapi import HTTPException, UploadFile
from redis import Redis

from nvidia_rag.chat_gateway.models import (
    ChatMessageV1,
    ChatMode,
    ChatOrchestrationRequestV1,
    ChatOrchestrationResponseV1,
    IntakeJobRequestV1,
    IntakeJobResultV1,
    IntakeJobStatus,
    IntakeProfileV1,
    IntakeSourceType,
    StartupState,
    StartupStatusV1,
    StartupStepResultV1,
    ToolAdapterType,
    ToolCallRequestV1,
    ToolCallResultV1,
    ToolCallStatus,
    ToolManifestV1,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

ALLOWED_RAG_OVERRIDE_FIELDS = {
    "temperature",
    "top_p",
    "max_tokens",
    "reranker_top_k",
    "vdb_top_k",
    "enable_query_rewriting",
    "enable_filter_generator",
    "filter_expr",
    "confidence_threshold",
    "model",
    "llm_endpoint",
    "embedding_model",
    "embedding_endpoint",
    "reranker_model",
    "reranker_endpoint",
    "vlm_model",
    "vlm_endpoint",
}


def _load_yaml_or_json(path: Path) -> Any:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _normalize_extensions(extensions: list[str]) -> set[str]:
    normalized: set[str] = set()
    for ext in extensions:
        e = ext.strip().lower()
        if not e:
            continue
        normalized.add(e if e.startswith(".") else f".{e}")
    return normalized


def _message_to_text(message: ChatMessageV1) -> str:
    if isinstance(message.content, str):
        return message.content
    text_parts: list[str] = []
    for entry in message.content:
        if isinstance(entry, dict) and entry.get("type") == "text":
            text = entry.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "\n".join(part for part in text_parts if part.strip())


def _parse_sse_data_lines(raw_text: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse streamed SSE response from /v1/generate into answer and chunks."""
    answer_parts: list[str] = []
    chunks: list[dict[str, Any]] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            payload = line[5:].strip()
        else:
            payload = line
        if not payload or payload == "[DONE]":
            continue
        try:
            data = json.loads(payload)
            chunks.append(data)
        except json.JSONDecodeError:
            continue
        try:
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                answer_parts.append(str(content))
        except Exception:
            continue
    return "".join(answer_parts), chunks


@dataclass
class GatewaySettings:
    """Runtime settings for chat gateway."""

    rag_base_url: str
    ingestor_base_url: str
    milvus_endpoint: str
    mcp_url: str
    mcp_transport: str
    mcp_client_command: str
    mcp_client_args: str
    request_timeout_seconds: float
    tool_timeout_seconds: float
    max_tool_output_bytes: int
    intake_profiles_file: str
    tool_manifest_file: str
    metadata_schema_file: str
    default_collection_name: str
    collection_embedding_dimension: int
    auto_startup_bootstrap: bool
    startup_fail_closed: bool
    store_backend: str
    redis_host: str
    redis_port: int
    redis_db: int
    redis_key_prefix: str
    redis_session_ttl_seconds: int
    redis_job_ttl_seconds: int
    redis_startup_ttl_seconds: int

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            rag_base_url=os.getenv("KORDA_CHAT_RAG_BASE_URL", "http://localhost:8081/v1").rstrip("/"),
            ingestor_base_url=os.getenv("KORDA_CHAT_INGESTOR_BASE_URL", "http://localhost:8082/v1").rstrip("/"),
            milvus_endpoint=os.getenv("KORDA_CHAT_MILVUS_ENDPOINT", "http://milvus:19530"),
            mcp_url=os.getenv("KORDA_CHAT_MCP_URL", "http://localhost:8000/mcp").rstrip("/"),
            mcp_transport=os.getenv("KORDA_CHAT_MCP_TRANSPORT", "streamable_http"),
            mcp_client_command=os.getenv("KORDA_CHAT_MCP_CLIENT_COMMAND", "python"),
            mcp_client_args=os.getenv("KORDA_CHAT_MCP_CLIENT_ARGS", ""),
            request_timeout_seconds=float(os.getenv("KORDA_CHAT_REQUEST_TIMEOUT_SECONDS", "120")),
            tool_timeout_seconds=float(os.getenv("KORDA_CHAT_TOOL_TIMEOUT_SECONDS", "20")),
            max_tool_output_bytes=int(os.getenv("KORDA_CHAT_MAX_TOOL_OUTPUT_BYTES", "262144")),
            intake_profiles_file=os.getenv(
                "KORDA_CHAT_INTAKE_PROFILES_FILE",
                "/workspace/deploy/config/korda-intake-profiles.yaml",
            ),
            tool_manifest_file=os.getenv(
                "KORDA_CHAT_TOOL_MANIFEST_FILE",
                "/workspace/deploy/config/korda-tool-manifest.yaml",
            ),
            metadata_schema_file=os.getenv(
                "KORDA_CHAT_METADATA_SCHEMA_FILE",
                "/workspace/deploy/config/korda-epc-metadata-schema.json",
            ),
            default_collection_name=os.getenv(
                "KORDA_CHAT_DEFAULT_COLLECTION_NAME",
                "korda-epc-default-dev",
            ),
            collection_embedding_dimension=int(
                os.getenv("KORDA_CHAT_COLLECTION_EMBEDDING_DIMENSION", "2048")
            ),
            auto_startup_bootstrap=os.getenv(
                "KORDA_CHAT_AUTO_STARTUP_BOOTSTRAP", "true"
            ).lower()
            == "true",
            startup_fail_closed=os.getenv("KORDA_CHAT_STARTUP_FAIL_CLOSED", "true").lower() == "true",
            store_backend=os.getenv("KORDA_CHAT_STORE_BACKEND", "redis").lower(),
            redis_host=os.getenv("KORDA_CHAT_REDIS_HOST", os.getenv("REDIS_HOST", "redis")),
            redis_port=int(os.getenv("KORDA_CHAT_REDIS_PORT", os.getenv("REDIS_PORT", "6379"))),
            redis_db=int(os.getenv("KORDA_CHAT_REDIS_DB", os.getenv("REDIS_DB", "0"))),
            redis_key_prefix=os.getenv("KORDA_CHAT_REDIS_KEY_PREFIX", "korda:chat-gateway:v1"),
            redis_session_ttl_seconds=int(
                os.getenv("KORDA_CHAT_SESSION_TTL_SECONDS", str(14 * 24 * 60 * 60))
            ),
            redis_job_ttl_seconds=int(
                os.getenv("KORDA_CHAT_JOB_TTL_SECONDS", str(30 * 24 * 60 * 60))
            ),
            redis_startup_ttl_seconds=int(os.getenv("KORDA_CHAT_STARTUP_TTL_SECONDS", "0")),
        )


class GatewayStore(Protocol):
    """Storage protocol for jobs, sessions, and startup state."""

    async def upsert_job(self, job: IntakeJobResultV1) -> None: ...

    async def get_job(self, job_id: str) -> IntakeJobResultV1 | None: ...

    async def append_session_event(self, session_id: str, event: dict[str, Any]) -> None: ...

    async def get_session_events(self, session_id: str) -> list[dict[str, Any]]: ...

    async def set_startup_status(self, status: StartupStatusV1) -> None: ...

    async def get_startup_status(self) -> StartupStatusV1 | None: ...


class InMemoryStore:
    """Fallback in-memory job/session/startup store for gateway state."""

    def __init__(self) -> None:
        self._jobs: dict[str, IntakeJobResultV1] = {}
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        self._startup_status: StartupStatusV1 | None = None
        self._lock = asyncio.Lock()

    async def upsert_job(self, job: IntakeJobResultV1) -> None:
        async with self._lock:
            self._jobs[job.job_id] = job

    async def get_job(self, job_id: str) -> IntakeJobResultV1 | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def append_session_event(self, session_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = []
            self._sessions[session_id].append(event)

    async def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._sessions.get(session_id, []))

    async def set_startup_status(self, status: StartupStatusV1) -> None:
        async with self._lock:
            self._startup_status = status

    async def get_startup_status(self) -> StartupStatusV1 | None:
        async with self._lock:
            return self._startup_status


class RedisStore:
    """Redis-backed store for restart-safe jobs, sessions, and startup state."""

    def __init__(self, settings: GatewaySettings) -> None:
        self.settings = settings
        self.redis = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        # Verify at init; caller can handle fallback if unavailable.
        self.redis.ping()

    def _job_key(self, job_id: str) -> str:
        return f"{self.settings.redis_key_prefix}:job:{job_id}"

    def _session_key(self, session_id: str) -> str:
        return f"{self.settings.redis_key_prefix}:session:{session_id}:events"

    def _startup_key(self) -> str:
        return f"{self.settings.redis_key_prefix}:startup:status"

    async def upsert_job(self, job: IntakeJobResultV1) -> None:
        payload = job.model_dump_json()
        ttl = self.settings.redis_job_ttl_seconds

        def _write() -> None:
            if ttl > 0:
                self.redis.set(self._job_key(job.job_id), payload, ex=ttl)
            else:
                self.redis.set(self._job_key(job.job_id), payload)

        await asyncio.to_thread(_write)

    async def get_job(self, job_id: str) -> IntakeJobResultV1 | None:
        raw = await asyncio.to_thread(self.redis.get, self._job_key(job_id))
        if not raw:
            return None
        try:
            return IntakeJobResultV1.model_validate_json(raw)
        except Exception:
            return None

    async def append_session_event(self, session_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        ttl = self.settings.redis_session_ttl_seconds
        key = self._session_key(session_id)

        def _append() -> None:
            self.redis.rpush(key, payload)
            if ttl > 0:
                self.redis.expire(key, ttl)

        await asyncio.to_thread(_append)

    async def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        raw_events = await asyncio.to_thread(self.redis.lrange, self._session_key(session_id), 0, -1)
        parsed: list[dict[str, Any]] = []
        for entry in raw_events:
            try:
                item = json.loads(entry)
                if isinstance(item, dict):
                    parsed.append(item)
            except Exception:
                continue
        return parsed

    async def set_startup_status(self, status: StartupStatusV1) -> None:
        payload = status.model_dump_json()
        ttl = self.settings.redis_startup_ttl_seconds
        key = self._startup_key()

        def _write() -> None:
            if ttl > 0:
                self.redis.set(key, payload, ex=ttl)
            else:
                self.redis.set(key, payload)

        await asyncio.to_thread(_write)

    async def get_startup_status(self) -> StartupStatusV1 | None:
        raw = await asyncio.to_thread(self.redis.get, self._startup_key())
        if not raw:
            return None
        try:
            return StartupStatusV1.model_validate_json(raw)
        except Exception:
            return None


class ToolRegistry:
    """Loads and resolves tool manifests with allowlist behavior."""

    def __init__(self, settings: GatewaySettings):
        self.settings = settings
        self._manifests = self._load_manifests()
        allowed_tools = os.getenv("KORDA_CHAT_ALLOWED_TOOLS", "").strip()
        self._allowlist = {name.strip() for name in allowed_tools.split(",") if name.strip()}

    def _default_manifest(self) -> list[ToolManifestV1]:
        return [
            ToolManifestV1(
                name="search",
                description="Search indexed collections through MCP.",
                adapter_type=ToolAdapterType.MCP_STREAMABLE_HTTP,
            ),
            ToolManifestV1(
                name="generate",
                description="Generate answer through MCP.",
                adapter_type=ToolAdapterType.MCP_STREAMABLE_HTTP,
            ),
            ToolManifestV1(
                name="upload_documents",
                description="Upload documents through MCP ingestion tool.",
                adapter_type=ToolAdapterType.MCP_STREAMABLE_HTTP,
            ),
        ]

    def _load_manifests(self) -> dict[str, ToolManifestV1]:
        manifest_path = Path(self.settings.tool_manifest_file)
        manifests: list[ToolManifestV1] = []
        if manifest_path.exists():
            try:
                data = _load_yaml_or_json(manifest_path)
                if isinstance(data, dict):
                    data = data.get("tools", [])
                if isinstance(data, list):
                    manifests = [ToolManifestV1(**entry) for entry in data]
            except Exception as exc:
                logger.warning("Failed to parse tool manifest file %s: %s", manifest_path, exc)
        if not manifests:
            manifests = self._default_manifest()
        return {manifest.name: manifest for manifest in manifests}

    def list_tools(self) -> list[ToolManifestV1]:
        if not self._allowlist:
            return [manifest for manifest in self._manifests.values() if manifest.enabled]
        return [
            manifest
            for name, manifest in self._manifests.items()
            if manifest.enabled and name in self._allowlist
        ]

    def resolve_tool(self, requested_name: str) -> ToolManifestV1:
        manifest = self._manifests.get(requested_name)
        if not manifest:
            raise HTTPException(status_code=400, detail=f"Unknown tool '{requested_name}'")
        if not manifest.enabled:
            raise HTTPException(status_code=400, detail=f"Tool '{requested_name}' is disabled")
        if self._allowlist and requested_name not in self._allowlist:
            raise HTTPException(status_code=403, detail=f"Tool '{requested_name}' is not in allowlist")
        return manifest


class GatewayService:
    """Main orchestration service for chat and intake."""

    def __init__(self, settings: GatewaySettings):
        self.settings = settings
        self.store: GatewayStore = self._create_store()
        self.tools = ToolRegistry(settings)
        self.intake_profiles = self._load_intake_profiles()
        self._bootstrap_lock = asyncio.Lock()
        self._startup_status = StartupStatusV1(
            state=StartupState.NOT_RUN,
            run_reason="startup",
            default_collection_name=self.settings.default_collection_name,
        )

    def _create_store(self) -> GatewayStore:
        if self.settings.store_backend != "redis":
            return InMemoryStore()
        try:
            return RedisStore(self.settings)
        except Exception as exc:
            logger.warning("Redis store unavailable, falling back to memory store: %s", exc)
            return InMemoryStore()

    def _load_intake_profiles(self) -> dict[str, IntakeProfileV1]:
        profile_path = Path(self.settings.intake_profiles_file)
        if not profile_path.exists():
            logger.warning("Intake profiles file does not exist: %s", profile_path)
            return {}
        data = _load_yaml_or_json(profile_path)
        if isinstance(data, dict):
            data = data.get("profiles", [])
        profiles: dict[str, IntakeProfileV1] = {}
        if not isinstance(data, list):
            return profiles
        for entry in data:
            try:
                profile = IntakeProfileV1(**entry)
                profiles[profile.profile_id] = profile
            except Exception as exc:
                logger.warning("Skipping invalid intake profile entry: %s", exc)
        return profiles

    def get_profile(self, profile_id: str) -> IntakeProfileV1:
        profile = self.intake_profiles.get(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail=f"Unknown intake profile '{profile_id}'")
        return profile

    @staticmethod
    def _parse_tool_hint(text: str) -> str | None:
        lowered = text.strip().lower()
        for marker in ("tool:", "/tool ", "@tool "):
            if lowered.startswith(marker):
                return lowered[len(marker) :].split()[0].strip()
        return None

    def _plan_requested_tools(self, request: ChatOrchestrationRequestV1) -> list[ToolCallRequestV1]:
        if request.requested_tools:
            return request.requested_tools
        if request.mode != ChatMode.AUTO:
            return []
        user_text = _message_to_text(request.messages[-1])
        tool_hint = self._parse_tool_hint(user_text)
        if not tool_hint:
            return []
        try:
            self.tools.resolve_tool(tool_hint)
        except HTTPException:
            return []
        return [
            ToolCallRequestV1(
                tool_name=tool_hint,
                arguments={
                    "query": user_text,
                    "collection_names": request.collection_names,
                },
            )
        ]

    @staticmethod
    def resolve_chat_mode(request: ChatOrchestrationRequestV1, planned_tools: list[ToolCallRequestV1]) -> ChatMode:
        if request.mode != ChatMode.AUTO:
            return request.mode
        if planned_tools and request.use_knowledge_base:
            return ChatMode.RAG_PLUS_TOOL
        if planned_tools:
            return ChatMode.TOOL_ONLY
        return ChatMode.RAG_ONLY

    def _load_metadata_schema(self) -> list[dict[str, Any]]:
        metadata_path = Path(self.settings.metadata_schema_file)
        if not metadata_path.exists():
            return []
        data = _load_yaml_or_json(metadata_path)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            schema = data.get("metadata_schema", [])
            if isinstance(schema, list):
                return [item for item in schema if isinstance(item, dict)]
        return []

    async def _ensure_default_collection(self) -> tuple[bool, str]:
        metadata_schema = self._load_metadata_schema()
        created = False
        details = ""
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            # Try read-first path to keep bootstrap idempotent and avoid noisy create calls.
            try:
                list_resp = await client.get(
                    f"{self.settings.ingestor_base_url}/collections",
                    params={"vdb_endpoint": self.settings.milvus_endpoint},
                )
                if list_resp.is_success:
                    body = list_resp.json()
                    existing_names = {
                        entry.get("collection_name", "")
                        for entry in body.get("collections", [])
                        if isinstance(entry, dict)
                    }
                    if self.settings.default_collection_name in existing_names:
                        return False, "default collection already exists"
            except Exception as exc:
                logger.info("Collection pre-check skipped due to error: %s", exc)

            payload = {
                "collection_name": self.settings.default_collection_name,
                "vdb_endpoint": self.settings.milvus_endpoint,
                "metadata_schema": metadata_schema,
            }
            create_resp = await client.post(
                f"{self.settings.ingestor_base_url}/collection",
                json=payload,
            )
            if create_resp.is_success:
                created = True
                details = "default collection created"
            else:
                body_text = create_resp.text
                lowered = body_text.lower()
                if create_resp.status_code in {400, 409} and (
                    "already" in lowered or "exists" in lowered
                ):
                    created = False
                    details = "default collection already exists"
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=(
                            "Default collection bootstrap failed: "
                            f"status={create_resp.status_code} body={body_text[:500]}"
                        ),
                    )
        return created, details

    async def _check_dependency_health(self, base_url: str, name: str) -> str:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.get(f"{base_url}/health", params={"check_dependencies": "true"})
            response.raise_for_status()
            return f"{name} healthy"

    async def get_startup_status(self) -> StartupStatusV1:
        stored = await self.store.get_startup_status()
        if stored is not None:
            self._startup_status = stored
        return self._startup_status

    async def run_startup_bootstrap(self, run_reason: str = "manual") -> StartupStatusV1:
        async with self._bootstrap_lock:
            status = StartupStatusV1(
                state=StartupState.RUNNING,
                run_reason=run_reason,
                default_collection_name=self.settings.default_collection_name,
                app_degraded=False,
                started_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            await self.store.set_startup_status(status)
            self._startup_status = status

            async def run_step(step_name: str, fn: Any) -> tuple[bool, str]:
                start = time.perf_counter()
                try:
                    detail = await fn()
                    status.steps.append(
                        StartupStepResultV1(
                            step=step_name,
                            status="success",
                            duration_ms=int((time.perf_counter() - start) * 1000),
                            detail=str(detail),
                        )
                    )
                    return True, str(detail)
                except Exception as exc:
                    status.steps.append(
                        StartupStepResultV1(
                            step=step_name,
                            status="failed",
                            duration_ms=int((time.perf_counter() - start) * 1000),
                            detail=str(exc),
                        )
                    )
                    status.errors.append(f"{step_name}: {exc}")
                    return False, str(exc)

            await run_step(
                "ingestor_health",
                lambda: self._check_dependency_health(
                    self.settings.ingestor_base_url, "ingestor"
                ),
            )
            await run_step(
                "rag_health",
                lambda: self._check_dependency_health(self.settings.rag_base_url, "rag"),
            )

            async def _validate_profiles() -> str:
                if not Path(self.settings.intake_profiles_file).exists():
                    raise FileNotFoundError(
                        f"Missing intake profiles file: {self.settings.intake_profiles_file}"
                    )
                profiles = self._load_intake_profiles()
                if not profiles:
                    raise ValueError("No valid intake profiles loaded")
                self.intake_profiles = profiles
                return f"{len(profiles)} intake profiles loaded"

            async def _validate_manifest() -> str:
                path = Path(self.settings.tool_manifest_file)
                if not path.exists():
                    raise FileNotFoundError(
                        f"Missing tool manifest file: {self.settings.tool_manifest_file}"
                    )
                self.tools = ToolRegistry(self.settings)
                tools = self.tools.list_tools()
                if not tools:
                    raise ValueError("No enabled tools available")
                return f"{len(tools)} tools loaded"

            await run_step("validate_intake_profiles", _validate_profiles)
            await run_step("validate_tool_manifest", _validate_manifest)

            async def _ensure_collection_step() -> str:
                created, detail = await self._ensure_default_collection()
                status.default_collection_created = created
                return detail

            await run_step("ensure_default_collection", _ensure_collection_step)

            status.finished_at = utc_now_iso()
            status.updated_at = utc_now_iso()
            status.app_degraded = bool(status.errors) and self.settings.startup_fail_closed
            status.state = StartupState.FAILED if status.errors else StartupState.READY
            await self.store.set_startup_status(status)
            self._startup_status = status
            return status

    async def _invoke_tool_http_json(
        self, manifest: ToolManifestV1, request: ToolCallRequestV1
    ) -> ToolCallResultV1:
        if not manifest.endpoint:
            return ToolCallResultV1(
                tool_name=request.tool_name,
                status=ToolCallStatus.ERROR,
                latency_ms=0,
                error="Tool endpoint is required for adapter_type=http_json",
            )

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=manifest.timeout_seconds) as client:
                response = await client.post(manifest.endpoint, json=request.arguments)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException:
            return ToolCallResultV1(
                tool_name=request.tool_name,
                status=ToolCallStatus.TIMEOUT,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"Tool call timed out after {manifest.timeout_seconds}s",
            )
        except Exception as exc:
            return ToolCallResultV1(
                tool_name=request.tool_name,
                status=ToolCallStatus.ERROR,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=str(exc),
            )

        payload = json.dumps(data, ensure_ascii=False)
        if len(payload.encode("utf-8")) > manifest.max_output_bytes:
            data = {"truncated": True, "preview": payload[:manifest.max_output_bytes]}

        return ToolCallResultV1(
            tool_name=request.tool_name,
            status=ToolCallStatus.SUCCESS,
            latency_ms=int((time.perf_counter() - start) * 1000),
            output=data,
        )

    async def _invoke_tool_mcp(
        self, manifest: ToolManifestV1, request: ToolCallRequestV1
    ) -> ToolCallResultV1:
        start = time.perf_counter()
        repo_root = Path(__file__).resolve().parents[3]
        mcp_client_script = repo_root / "examples" / "nvidia_rag_mcp" / "mcp_client.py"
        url = manifest.endpoint or self.settings.mcp_url
        cmd = [
            self.settings.mcp_client_command,
            str(mcp_client_script),
            "call",
            "--transport",
            self.settings.mcp_transport,
            "--url",
            url,
            "--tool",
            request.tool_name,
            "--json-args",
            json.dumps(request.arguments),
        ]
        if self.settings.mcp_client_args.strip():
            cmd.extend(self.settings.mcp_client_args.split())

        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=manifest.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ToolCallResultV1(
                tool_name=request.tool_name,
                status=ToolCallStatus.TIMEOUT,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=f"MCP call timed out after {manifest.timeout_seconds}s",
            )
        except Exception as exc:
            return ToolCallResultV1(
                tool_name=request.tool_name,
                status=ToolCallStatus.ERROR,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=str(exc),
            )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0:
            return ToolCallResultV1(
                tool_name=request.tool_name,
                status=ToolCallStatus.ERROR,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=stderr or stdout or f"MCP client failed with code {completed.returncode}",
            )

        try:
            output: Any = json.loads(stdout)
        except Exception:
            output = {"raw": stdout}

        serialized = json.dumps(output, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > manifest.max_output_bytes:
            output = {"truncated": True, "preview": serialized[:manifest.max_output_bytes]}

        return ToolCallResultV1(
            tool_name=request.tool_name,
            status=ToolCallStatus.SUCCESS,
            latency_ms=int((time.perf_counter() - start) * 1000),
            output=output,
        )

    async def call_tool(self, tool_request: ToolCallRequestV1) -> ToolCallResultV1:
        manifest = self.tools.resolve_tool(tool_request.tool_name)
        if manifest.adapter_type == ToolAdapterType.HTTP_JSON:
            return await self._invoke_tool_http_json(manifest, tool_request)
        return await self._invoke_tool_mcp(manifest, tool_request)

    async def _call_rag_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(f"{self.settings.rag_base_url}/search", json=payload)
            response.raise_for_status()
            return response.json()

    async def _call_rag_generate(self, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(f"{self.settings.rag_base_url}/generate", json=payload)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            raw_text = response.text
            if "text/event-stream" in content_type:
                answer, chunks = _parse_sse_data_lines(raw_text)
                return answer, {"chunks": chunks}
            try:
                body = response.json()
            except Exception:
                return raw_text, {"raw": raw_text}

            answer = (
                body.get("answer")
                or body.get("choices", [{}])[0].get("message", {}).get("content", "")
                or ""
            )
            return str(answer), body

    def _build_rag_payload(
        self,
        request: ChatOrchestrationRequestV1,
        tool_calls: list[ToolCallResultV1],
        mode_resolved: ChatMode,
    ) -> dict[str, Any]:
        messages = [message.model_dump() for message in request.messages]
        if mode_resolved == ChatMode.RAG_PLUS_TOOL and tool_calls:
            # Add tool context as a deterministic system message to ground final answer.
            tool_context = []
            for result in tool_calls:
                tool_context.append(
                    {
                        "tool": result.tool_name,
                        "status": result.status.value,
                        "output": result.output,
                        "error": result.error,
                    }
                )
            messages = messages + [
                {
                    "role": "system",
                    "content": (
                        "Tool execution context (JSON). Use this as supplemental evidence only:\n"
                        + json.dumps(tool_context, ensure_ascii=False)
                    ),
                }
            ]

        payload: dict[str, Any] = {
            "messages": messages,
            "use_knowledge_base": request.use_knowledge_base,
            "enable_citations": request.enable_citations,
            "collection_names": request.collection_names,
        }
        if request.enable_reranker is not None:
            payload["enable_reranker"] = request.enable_reranker

        for key, value in request.rag_request_overrides.items():
            if key in ALLOWED_RAG_OVERRIDE_FIELDS:
                payload[key] = value

        return payload

    async def orchestrate_chat(
        self, request: ChatOrchestrationRequestV1
    ) -> ChatOrchestrationResponseV1:
        planned_tools = self._plan_requested_tools(request)
        mode_resolved = self.resolve_chat_mode(request, planned_tools)
        session_id = request.session_id or uuid4().hex
        warnings: list[str] = []

        tool_results: list[ToolCallResultV1] = []
        if mode_resolved in {ChatMode.TOOL_ONLY, ChatMode.RAG_PLUS_TOOL}:
            for tool_request in planned_tools:
                result = await self.call_tool(tool_request)
                tool_results.append(result)
                if result.status != ToolCallStatus.SUCCESS:
                    warnings.append(
                        f"Tool {result.tool_name} status={result.status.value}: {result.error or 'no details'}"
                    )

        citations: list[dict[str, Any]] = []
        rag_response: dict[str, Any] | None = None
        answer = ""
        if mode_resolved in {ChatMode.RAG_ONLY, ChatMode.RAG_PLUS_TOOL}:
            rag_payload = self._build_rag_payload(request, tool_results, mode_resolved)
            try:
                if request.enable_citations:
                    user_text = _message_to_text(request.messages[-1])
                    search_payload = {
                        "query": user_text,
                        "collection_names": request.collection_names,
                        "enable_reranker": request.enable_reranker
                        if request.enable_reranker is not None
                        else True,
                    }
                    search_response = await self._call_rag_search(search_payload)
                    if isinstance(search_response, dict):
                        citations = (
                            search_response.get("citations")
                            or search_response.get("results")
                            or []
                        )
                answer, rag_response = await self._call_rag_generate(rag_payload)
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"RAG call failed: {exc}") from exc

        if mode_resolved == ChatMode.TOOL_ONLY:
            # Tool-only mode produces a deterministic JSON summary as answer.
            answer = json.dumps([result.model_dump() for result in tool_results], ensure_ascii=False)

        response = ChatOrchestrationResponseV1(
            session_id=session_id,
            mode_resolved=mode_resolved,
            answer=answer,
            citations=citations,
            tool_calls=tool_results,
            warnings=warnings,
            rag_response=rag_response,
        )
        await self.store.append_session_event(
            session_id,
            {
                "timestamp": utc_now_iso(),
                "request": request.model_dump(),
                "planned_tools": [tool.model_dump() for tool in planned_tools],
                "response": response.model_dump(),
            },
        )
        return response

    def _validate_profile_extensions(
        self, profile: IntakeProfileV1, file_names: list[str]
    ) -> list[dict[str, Any]]:
        allowed = _normalize_extensions(profile.allowed_extensions)
        if not allowed:
            return []
        errors: list[dict[str, Any]] = []
        for file_name in file_names:
            ext = Path(file_name).suffix.lower()
            if ext not in allowed:
                errors.append(
                    {
                        "file": file_name,
                        "code": "UNSUPPORTED_EXTENSION_FOR_PROFILE",
                        "message": f"{ext} is not allowed for profile {profile.profile_id}",
                    }
                )
        return errors

    def _validate_required_metadata(
        self, profile: IntakeProfileV1, custom_metadata: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not profile.required_metadata_fields:
            return []
        errors: list[dict[str, Any]] = []
        by_filename: dict[str, dict[str, Any]] = {}
        for item in custom_metadata:
            filename = str(item.get("filename", ""))
            metadata = item.get("metadata", {})
            if filename and isinstance(metadata, dict):
                by_filename[filename] = metadata

        for filename, metadata in by_filename.items():
            missing = [
                field_name
                for field_name in profile.required_metadata_fields
                if field_name not in metadata or metadata[field_name] in (None, "", [])
            ]
            if missing:
                errors.append(
                    {
                        "file": filename,
                        "code": "MISSING_REQUIRED_METADATA_FIELDS",
                        "message": f"Missing fields: {', '.join(missing)}",
                    }
                )
        return errors

    async def _call_ingestor_upload(
        self,
        payload: dict[str, Any],
        files: list[tuple[str, bytes, str]],
    ) -> dict[str, Any]:
        multipart_files: list[tuple[str, tuple[str | None, bytes | str, str]]] = []
        for filename, content, content_type in files:
            multipart_files.append(("documents", (filename, content, content_type)))
        multipart_files.append(("data", (None, json.dumps(payload), "application/json")))

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.ingestor_base_url}/documents",
                files=multipart_files,
            )
            response.raise_for_status()
            return response.json()

    async def intake_upload(
        self,
        profile_id: str,
        collection_name: str,
        files: list[UploadFile],
        blocking: bool,
        custom_metadata: list[dict[str, Any]] | None = None,
        generate_summary_override: bool | None = None,
    ) -> dict[str, Any]:
        profile = self.get_profile(profile_id)
        custom_metadata = custom_metadata or []
        file_names = [file.filename or f"file-{idx}" for idx, file in enumerate(files)]

        validation_errors = []
        validation_errors.extend(self._validate_profile_extensions(profile, file_names))
        validation_errors.extend(self._validate_required_metadata(profile, custom_metadata))
        if validation_errors:
            return {
                "status": "validation_failed",
                "validation_errors": validation_errors,
                "failed_documents": file_names,
            }

        prepared_files: list[tuple[str, bytes, str]] = []
        for index, file in enumerate(files):
            content = await file.read()
            prepared_files.append(
                (
                    file.filename or f"file-{index}",
                    content,
                    file.content_type or "application/octet-stream",
                )
            )

        payload = {
            "collection_name": collection_name,
            "blocking": blocking,
            "split_options": profile.split_options,
            "custom_metadata": custom_metadata,
            "generate_summary": (
                generate_summary_override
                if generate_summary_override is not None
                else profile.generate_summary
            ),
        }
        return await self._call_ingestor_upload(payload=payload, files=prepared_files)

    async def _discover_bulk_files(self, request: IntakeJobRequestV1) -> list[Path]:
        if request.files:
            return [Path(path) for path in request.files]

        if request.source_type not in {
            IntakeSourceType.FILESYSTEM,
            IntakeSourceType.CONNECTOR_PULL,
        }:
            raise HTTPException(
                status_code=400,
                detail=f"source_type '{request.source_type.value}' is not yet implemented",
            )
        if not request.source_uri:
            raise HTTPException(status_code=400, detail="source_uri is required for filesystem bulk intake")

        source_path = Path(request.source_uri)
        if not source_path.exists():
            raise HTTPException(status_code=404, detail=f"source_uri does not exist: {source_path}")
        if not source_path.is_dir():
            raise HTTPException(status_code=400, detail=f"source_uri is not a directory: {source_path}")

        files = [path for path in source_path.rglob("*") if path.is_file()]
        files.sort()
        return files[: request.max_files]

    async def _run_bulk_job(self, job: IntakeJobResultV1) -> IntakeJobResultV1:
        request = job.request
        profile = self.get_profile(request.profile_id)
        job.status = IntakeJobStatus.RUNNING
        job.updated_at = utc_now_iso()
        await self.store.upsert_job(job)

        try:
            file_paths = await self._discover_bulk_files(request)
            file_names = [path.name for path in file_paths]
            job.validation_errors.extend(self._validate_profile_extensions(profile, file_names))
            if job.validation_errors:
                job.status = IntakeJobStatus.FAILED
                job.failed_files = [{"file": item["file"], "error": item["message"]} for item in job.validation_errors]
                job.error = "Bulk validation failed"
                job.updated_at = utc_now_iso()
                await self.store.upsert_job(job)
                return job

            files_for_upload: list[tuple[str, bytes, str]] = []
            for file_path in file_paths:
                files_for_upload.append((file_path.name, file_path.read_bytes(), "application/octet-stream"))

            payload = {
                "collection_name": request.collection_name,
                "blocking": request.blocking,
                "split_options": profile.split_options,
                "custom_metadata": request.custom_metadata,
                "generate_summary": (
                    request.generate_summary_override
                    if request.generate_summary_override is not None
                    else profile.generate_summary
                ),
            }
            response = await self._call_ingestor_upload(payload=payload, files=files_for_upload)
            task_id = response.get("task_id")
            if task_id:
                job.ingestor_task_ids.append(task_id)
            if response.get("result", {}).get("failed_documents"):
                job.failed_files = response["result"]["failed_documents"]
            job.processed_files = file_names
            job.status = IntakeJobStatus.SUCCESS if not job.failed_files else IntakeJobStatus.FAILED
            if job.failed_files and not job.error:
                job.error = "Some files failed during ingestion"
        except Exception as exc:
            job.status = IntakeJobStatus.FAILED
            job.error = str(exc)
        finally:
            job.updated_at = utc_now_iso()
            await self.store.upsert_job(job)
        return job

    async def submit_bulk_job(self, request: IntakeJobRequestV1) -> IntakeJobResultV1:
        # Fail early on unknown profile.
        self.get_profile(request.profile_id)
        job = IntakeJobResultV1(request=request)
        await self.store.upsert_job(job)
        if request.blocking:
            return await self._run_bulk_job(job)
        asyncio.create_task(self._run_bulk_job(job))
        return job
