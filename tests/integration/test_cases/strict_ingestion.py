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

"""Strict ingestion smoke tests for validation/error response surfaces."""

import json
import logging
import os
import time

import aiohttp

from ..base import BaseTestModule, TestStatus, test_case
from ..utils.file_utils import get_test_files

logger = logging.getLogger(__name__)


class StrictIngestionModule(BaseTestModule):
    """Strict ingestion smoke tests."""

    COLLECTION_NAME = "strict_ingestion_smoke"

    def _pick_test_file(self) -> str | None:
        files = get_test_files(
            self.test_runner.data_dir,
            count=1,
            collection_type="without_metadata",
            files_with_metadata=self.test_runner.files_with_metadata,
            files_without_metadata=self.test_runner.files_without_metadata,
        )
        return files[0] if files else None

    @test_case(115, "Create Strict Ingestion Collection")
    async def _test_create_strict_ingestion_collection(self) -> bool:
        start = time.time()
        payload = {
            "collection_name": self.COLLECTION_NAME,
            "embedding_dimension": 2048,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ingestor_server_url}/v1/collection", json=payload
                ) as response:
                    data = await response.json()
                    if response.status == 200:
                        self.add_test_result(
                            self._test_create_strict_ingestion_collection.test_number,
                            self._test_create_strict_ingestion_collection.test_name,
                            "Create collection for strict-ingestion smoke checks.",
                            ["POST /v1/collection"],
                            ["collection_name", "embedding_dimension"],
                            time.time() - start,
                            TestStatus.SUCCESS,
                        )
                        logger.info("Created strict-ingestion collection: %s", data)
                        return True

                    self.add_test_result(
                        self._test_create_strict_ingestion_collection.test_number,
                        self._test_create_strict_ingestion_collection.test_name,
                        "Create collection for strict-ingestion smoke checks.",
                        ["POST /v1/collection"],
                        ["collection_name", "embedding_dimension"],
                        time.time() - start,
                        TestStatus.FAILURE,
                        f"Unexpected status: {response.status}, response: {data}",
                    )
                    return False
        except Exception as exc:
            self.add_test_result(
                self._test_create_strict_ingestion_collection.test_number,
                self._test_create_strict_ingestion_collection.test_name,
                "Create collection for strict-ingestion smoke checks.",
                ["POST /v1/collection"],
                ["collection_name", "embedding_dimension"],
                time.time() - start,
                TestStatus.FAILURE,
                str(exc),
            )
            return False

    @test_case(116, "Strict Ingestion Response Surfaces")
    async def _test_strict_ingestion_response_surfaces(self) -> bool:
        """Verify canonical response fields exist after upload for strict mode diagnostics."""
        start = time.time()
        test_file = self._pick_test_file()
        if not test_file:
            self.add_test_result(
                self._test_strict_ingestion_response_surfaces.test_number,
                self._test_strict_ingestion_response_surfaces.test_name,
                "Upload one file and verify strict-ingestion response surfaces.",
                ["POST /v1/documents"],
                ["failed_documents", "validation_errors"],
                time.time() - start,
                TestStatus.FAILURE,
                "No test file available for strict-ingestion smoke test",
            )
            return False

        upload_payload = {
            "collection_name": self.COLLECTION_NAME,
            "blocking": True,
            "split_options": {"chunk_size": 512, "chunk_overlap": 150},
            "custom_metadata": [],
            "generate_summary": True,
            "summary_options": {"summarization_strategy": "single"},
        }

        try:
            form_data = aiohttp.FormData()
            with open(test_file, "rb") as file_handle:
                file_bytes = file_handle.read()

            form_data.add_field(
                "documents",
                file_bytes,
                filename=os.path.basename(test_file),
                content_type="application/octet-stream",
            )
            form_data.add_field(
                "data",
                json.dumps(upload_payload),
                content_type="application/json",
            )

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ingestor_server_url}/v1/documents",
                    data=form_data,
                ) as response:
                    result = await response.json()
                    if response.status != 200:
                        self.add_test_result(
                            self._test_strict_ingestion_response_surfaces.test_number,
                            self._test_strict_ingestion_response_surfaces.test_name,
                            "Upload one file and verify strict-ingestion response surfaces.",
                            ["POST /v1/documents"],
                            ["failed_documents", "validation_errors"],
                            time.time() - start,
                            TestStatus.FAILURE,
                            f"Unexpected status: {response.status}, response: {result}",
                        )
                        return False

                    # Canonical surfaces required for strict mode diagnostics.
                    if (
                        "failed_documents" not in result
                        or "validation_errors" not in result
                        or not isinstance(result["failed_documents"], list)
                        or not isinstance(result["validation_errors"], list)
                    ):
                        self.add_test_result(
                            self._test_strict_ingestion_response_surfaces.test_number,
                            self._test_strict_ingestion_response_surfaces.test_name,
                            "Upload one file and verify strict-ingestion response surfaces.",
                            ["POST /v1/documents"],
                            ["failed_documents", "validation_errors"],
                            time.time() - start,
                            TestStatus.FAILURE,
                            f"Missing canonical response fields: {result}",
                        )
                        return False

                    logger.info(
                        "Strict smoke response: failed_documents=%d, validation_errors=%d",
                        len(result["failed_documents"]),
                        len(result["validation_errors"]),
                    )
                    self.add_test_result(
                        self._test_strict_ingestion_response_surfaces.test_number,
                        self._test_strict_ingestion_response_surfaces.test_name,
                        "Upload one file and verify strict-ingestion response surfaces.",
                        ["POST /v1/documents"],
                        ["failed_documents", "validation_errors"],
                        time.time() - start,
                        TestStatus.SUCCESS,
                    )
                    return True
        except Exception as exc:
            self.add_test_result(
                self._test_strict_ingestion_response_surfaces.test_number,
                self._test_strict_ingestion_response_surfaces.test_name,
                "Upload one file and verify strict-ingestion response surfaces.",
                ["POST /v1/documents"],
                ["failed_documents", "validation_errors"],
                time.time() - start,
                TestStatus.FAILURE,
                str(exc),
            )
            return False

    @test_case(117, "Delete Strict Ingestion Collection")
    async def _test_delete_strict_ingestion_collection(self) -> bool:
        start = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                params = {"collection_names": [self.COLLECTION_NAME]}
                async with session.delete(
                    f"{self.ingestor_server_url}/v1/collections",
                    params=params,
                ) as response:
                    data = await response.json()
                    if response.status == 200:
                        self.add_test_result(
                            self._test_delete_strict_ingestion_collection.test_number,
                            self._test_delete_strict_ingestion_collection.test_name,
                            "Delete strict-ingestion smoke collection.",
                            ["DELETE /v1/collections"],
                            ["collection_names"],
                            time.time() - start,
                            TestStatus.SUCCESS,
                        )
                        logger.info("Deleted strict-ingestion collection: %s", data)
                        return True

                    self.add_test_result(
                        self._test_delete_strict_ingestion_collection.test_number,
                        self._test_delete_strict_ingestion_collection.test_name,
                        "Delete strict-ingestion smoke collection.",
                        ["DELETE /v1/collections"],
                        ["collection_names"],
                        time.time() - start,
                        TestStatus.FAILURE,
                        f"Unexpected status: {response.status}, response: {data}",
                    )
                    return False
        except Exception as exc:
            self.add_test_result(
                self._test_delete_strict_ingestion_collection.test_number,
                self._test_delete_strict_ingestion_collection.test_name,
                "Delete strict-ingestion smoke collection.",
                ["DELETE /v1/collections"],
                ["collection_names"],
                time.time() - start,
                TestStatus.FAILURE,
                str(exc),
            )
            return False
