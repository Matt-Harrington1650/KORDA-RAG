import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCollections } from "../api/useCollectionsApi";
import { useCollectionsStore } from "../store/useCollectionsStore";

interface GatewayStartupStatus {
  state: "not_run" | "running" | "ready" | "failed";
  default_collection_name?: string;
  app_degraded?: boolean;
}

async function fetchOptionalJson(path: string) {
  try {
    const res = await fetch(path);
    if (!res.ok) {
      return null;
    }
    return await res.json();
  } catch {
    return null;
  }
}

export function useGatewayStartupInitialization() {
  const { data: collections = [] } = useCollections();
  const { selectedCollections, setSelectedCollections } = useCollectionsStore();

  const startupQuery = useQuery({
    queryKey: ["gateway-startup-status"],
    queryFn: () => fetchOptionalJson("/api/startup/status") as Promise<GatewayStartupStatus | null>,
    retry: false,
    refetchInterval: 30000,
  });

  // Load tool/profile contracts on app open for startup handshake readiness.
  useQuery({
    queryKey: ["gateway-tools"],
    queryFn: () => fetchOptionalJson("/api/tools"),
    retry: false,
    staleTime: 30000,
  });
  useQuery({
    queryKey: ["gateway-intake-profiles"],
    queryFn: () => fetchOptionalJson("/api/intake/profiles"),
    retry: false,
    staleTime: 30000,
  });

  useEffect(() => {
    const defaultCollection = startupQuery.data?.default_collection_name;
    if (!defaultCollection || selectedCollections.length > 0) {
      return;
    }
    const exists = collections.some(
      (collection: { collection_name: string }) => collection.collection_name === defaultCollection
    );
    if (exists) {
      setSelectedCollections([defaultCollection]);
    }
  }, [startupQuery.data, selectedCollections, collections, setSelectedCollections]);

  return startupQuery.data;
}
