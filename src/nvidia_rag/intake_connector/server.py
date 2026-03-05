# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Connector worker for scheduled intake pulls into KORDA chat gateway."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO").upper())
logger = logging.getLogger(__name__)


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class ConnectorDefinition(BaseModel):
    """Declarative connector configuration."""

    connector_id: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    source_type: str = "filesystem"
    source_uri: str = Field(default="", max_length=2048)
    profile_id: str = Field(min_length=1, max_length=128)
    collection_name: str = Field(min_length=1, max_length=256)
    file_glob: str = "**/*"
    max_files_per_run: int = Field(default=200, ge=1, le=5000)


@dataclass
class ConnectorSettings:
    """Runtime settings for connector worker."""

    gateway_base_url: str
    config_file: str
    state_file: str
    poll_seconds: int
    autostart: bool
    warm_run_on_start: bool

    @classmethod
    def from_env(cls) -> "ConnectorSettings":
        return cls(
            gateway_base_url=os.getenv("KORDA_GATEWAY_BASE_URL", "http://localhost:8083/v1").rstrip("/"),
            config_file=os.getenv(
                "KORDA_CONNECTOR_CONFIG_FILE",
                "/workspace/deploy/config/korda-connectors.yaml",
            ),
            state_file=os.getenv(
                "KORDA_CONNECTOR_STATE_FILE",
                "/tmp-data/korda-connector-state.json",
            ),
            poll_seconds=int(os.getenv("KORDA_CONNECTOR_POLL_SECONDS", "300")),
            autostart=os.getenv("KORDA_CONNECTOR_AUTOSTART", "false").lower() == "true",
            warm_run_on_start=os.getenv("KORDA_CONNECTOR_WARM_RUN_ON_START", "true").lower() == "true",
        )


class ConnectorWorker:
    """Pulls files from connector sources and submits bulk jobs to gateway."""

    def __init__(self, settings: ConnectorSettings):
        self.settings = settings
        self._running = False
        self._task: asyncio.Task | None = None
        self._runs: list[dict[str, Any]] = []
        self._seen_hashes = self._load_seen_hashes()
        self._lock = asyncio.Lock()

    def _load_seen_hashes(self) -> dict[str, str]:
        state_path = Path(self.settings.state_file)
        if not state_path.exists():
            return {}
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw_hashes = data.get("seen_hashes", {})
                if isinstance(raw_hashes, dict):
                    return {str(k): str(v) for k, v in raw_hashes.items()}
        except Exception as exc:
            logger.warning("Failed to load connector state file %s: %s", state_path, exc)
        return {}

    def _persist_seen_hashes(self) -> None:
        state_path = Path(self.settings.state_file)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen_hashes": self._seen_hashes, "updated_at": _utc_now()}
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _file_fingerprint(self, path: Path) -> str:
        h = hashlib.sha256()
        stat = path.stat()
        h.update(str(path).encode("utf-8"))
        h.update(str(stat.st_mtime_ns).encode("utf-8"))
        h.update(str(stat.st_size).encode("utf-8"))
        return h.hexdigest()

    def _load_connectors(self) -> list[ConnectorDefinition]:
        config_path = Path(self.settings.config_file)
        if not config_path.exists():
            logger.warning("Connector config not found: %s", config_path)
            return []
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        connector_entries = raw.get("connectors", [])
        connectors: list[ConnectorDefinition] = []
        for entry in connector_entries:
            try:
                connectors.append(ConnectorDefinition(**entry))
            except Exception as exc:
                logger.warning("Skipping invalid connector entry: %s", exc)
        return connectors

    def _discover_new_files(self, connector: ConnectorDefinition) -> list[Path]:
        if connector.source_type != "filesystem":
            logger.warning(
                "Connector %s source_type=%s not implemented. Skipping.",
                connector.connector_id,
                connector.source_type,
            )
            return []
        source = Path(connector.source_uri)
        if not source.exists() or not source.is_dir():
            logger.warning(
                "Connector %s source_uri is invalid: %s",
                connector.connector_id,
                connector.source_uri,
            )
            return []
        candidates = [path for path in source.glob(connector.file_glob) if path.is_file()]
        candidates.sort()
        new_files: list[Path] = []
        for path in candidates:
            fp = self._file_fingerprint(path)
            if self._seen_hashes.get(str(path)) == fp:
                continue
            new_files.append(path)
            if len(new_files) >= connector.max_files_per_run:
                break
        return new_files

    async def _submit_bulk_job(self, connector: ConnectorDefinition, files: list[Path]) -> dict[str, Any]:
        payload = {
            "schema_version": "korda.intake_job_request.v1",
            "profile_id": connector.profile_id,
            "collection_name": connector.collection_name,
            "source_type": "connector_pull",
            "source_uri": connector.source_uri,
            "files": [str(path) for path in files],
            "blocking": False,
            "custom_metadata": [],
            "max_files": connector.max_files_per_run,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.settings.gateway_base_url}/intake/bulk", json=payload)
            response.raise_for_status()
            return response.json()

    async def run_once(self) -> dict[str, Any]:
        connectors = [connector for connector in self._load_connectors() if connector.enabled]
        run_record: dict[str, Any] = {
            "started_at": _utc_now(),
            "connectors_checked": len(connectors),
            "jobs": [],
            "errors": [],
        }
        for connector in connectors:
            files = self._discover_new_files(connector)
            if not files:
                continue
            try:
                result = await self._submit_bulk_job(connector, files)
                run_record["jobs"].append(
                    {
                        "connector_id": connector.connector_id,
                        "job_id": result.get("job_id"),
                        "file_count": len(files),
                    }
                )
                for path in files:
                    self._seen_hashes[str(path)] = self._file_fingerprint(path)
            except Exception as exc:
                run_record["errors"].append(
                    {"connector_id": connector.connector_id, "error": str(exc)}
                )

        run_record["finished_at"] = _utc_now()
        async with self._lock:
            self._runs.append(run_record)
            # keep memory bounded
            self._runs = self._runs[-500:]
        self._persist_seen_hashes()
        return run_record

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.run_once()
            except Exception as exc:
                logger.error("Connector loop iteration failed: %s", exc)
            await asyncio.sleep(self.settings.poll_seconds)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def runs(self) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._runs)

    @property
    def is_running(self) -> bool:
        return self._running


SETTINGS = ConnectorSettings.from_env()
WORKER = ConnectorWorker(SETTINGS)

app = FastAPI(
    title="KORDA Intake Connector Worker",
    description="Scheduled connector pulls and bulk intake submission worker.",
    version="1.0.0",
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
    if SETTINGS.autostart:
        if SETTINGS.warm_run_on_start:
            try:
                await WORKER.run_once()
                logger.info("Connector warm run completed at startup.")
            except Exception as exc:
                logger.error("Connector warm run failed: %s", exc)
        await WORKER.start()
        logger.info("Connector worker autostart enabled.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await WORKER.stop()


@app.get("/v1/health")
async def health() -> dict[str, Any]:
    return {
        "message": "Connector worker is up.",
        "running": WORKER.is_running,
        "gateway_base_url": SETTINGS.gateway_base_url,
        "config_file": SETTINGS.config_file,
        "state_file": SETTINGS.state_file,
        "warm_run_on_start": SETTINGS.warm_run_on_start,
    }


@app.get("/v1/connectors")
async def connectors() -> dict[str, Any]:
    return {"connectors": [connector.model_dump() for connector in WORKER._load_connectors()]}


@app.get("/v1/runs")
async def runs() -> dict[str, Any]:
    return {"runs": await WORKER.runs()}


@app.post("/v1/run-once")
async def run_once() -> dict[str, Any]:
    return await WORKER.run_once()


@app.post("/v1/start")
async def start_worker() -> dict[str, Any]:
    await WORKER.start()
    return {"message": "Connector worker started", "running": WORKER.is_running}


@app.post("/v1/stop")
async def stop_worker() -> dict[str, Any]:
    await WORKER.stop()
    return {"message": "Connector worker stopped", "running": WORKER.is_running}


@app.get("/v1/configuration")
async def configuration() -> dict[str, Any]:
    if not Path(SETTINGS.config_file).exists():
        raise HTTPException(status_code=404, detail=f"Config file missing: {SETTINGS.config_file}")
    return {
        "gateway_base_url": SETTINGS.gateway_base_url,
        "config_file": SETTINGS.config_file,
        "state_file": SETTINGS.state_file,
        "poll_seconds": SETTINGS.poll_seconds,
        "autostart": SETTINGS.autostart,
        "warm_run_on_start": SETTINGS.warm_run_on_start,
    }
