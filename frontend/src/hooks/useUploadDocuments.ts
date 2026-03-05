// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useState } from "react";
import { useNotificationStore } from "../store/useNotificationStore";
import { useCollectionConfigStore } from "../store/useCollectionConfigStore";

const FALLBACK_STATUS_CODES = new Set([404, 502, 503, 504]);
const DEFAULT_PROFILE_ID = "epc_drawing_profile";

export function useUploadDocuments() {
  const { addTaskNotification } = useNotificationStore();
  const { getConfig } = useCollectionConfigStore();
  const [isPending, setIsPending] = useState(false);

  const mutate = (data: { files: File[]; metadata: Record<string, unknown> }, options: { onSuccess?: (data: unknown) => void; onError?: (error: Error) => void }) => {
    setIsPending(true);
    const formData = new FormData();
    data.files.forEach((file) => {
      formData.append("documents", file);
    });
    
    // Get collection-specific config for summarization setting
    const collectionName = String(data.metadata.collection_name);
    const collectionConfig = getConfig(collectionName);
    
    const gatewayPayload = {
      profile_id: String(data.metadata.profile_id || DEFAULT_PROFILE_ID),
      collection_name: collectionName,
      blocking: Boolean(data.metadata.blocking ?? false),
      custom_metadata: Array.isArray(data.metadata.custom_metadata) ? data.metadata.custom_metadata : [],
      generate_summary_override: collectionConfig.generateSummary,
    };
    formData.append("data", JSON.stringify(gatewayPayload));

    const fallbackFormData = new FormData();
    data.files.forEach((file) => {
      fallbackFormData.append("documents", file);
    });
    fallbackFormData.append(
      "data",
      JSON.stringify({ ...data.metadata, generate_summary: collectionConfig.generateSummary })
    );

    fetch(`/api/intake/upload`, {
      method: "POST",
      body: formData,
    })
      .then(async (res) => {
        if (!res.ok) {
          if (!FALLBACK_STATUS_CODES.has(res.status)) {
            throw new Error("Failed to upload documents");
          }
          const fallbackResponse = await fetch(`/api/documents?blocking=false`, {
            method: "POST",
            body: fallbackFormData,
          });
          if (!fallbackResponse.ok) {
            throw new Error("Failed to upload documents");
          }
          return fallbackResponse.json();
        }
        return res.json();
      })
      .then((responseData) => {
        if (responseData?.task_id) {
          const taskData = {
            id: responseData.task_id,
            collection_name: String(data.metadata.collection_name),
            documents: data.files.map((f) => f.name),
            state: "PENDING" as const,
            created_at: new Date().toISOString(),
          };

          addTaskNotification(taskData);
        }

        options.onSuccess?.(responseData);
      })
      .catch((error) => {
        options.onError?.(error);
      })
      .finally(() => {
        setIsPending(false);
      });
  };

  return { 
    mutate,
    isPending 
  };
}
