/**
 * API client for the Django Ninja backend.
 *
 * Uses relative URLs; Next.js rewrites in next.config.ts proxy /api/* and
 * /images/* to the Django backend. This file is a near-verbatim TypeScript
 * port of the Vite frontend's api.js.
 */

async function getErrorMessage(res: Response, fallback = `API error: ${res.status}`) {
  const err = await res.json().catch(() => ({ detail: res.statusText }));
  return err.detail || fallback;
}

async function request(path: string, options: RequestInit = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    throw new Error(await getErrorMessage(res, `API error: ${res.status}`));
  }
  return res;
}

// Properties
export const getProperties = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/properties/?${qs}`).then((r) => r.json());
};

export const getPriorityQueue = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/properties/priority-queue?${qs}`).then((r) => r.json());
};

export const getMapProperties = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/properties/map/all?${qs}`).then((r) => r.json());
};

export const getBuyerSummary = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/properties/buyers/summary?${qs}`).then((r) => r.json());
};

export const getPropertyClusters = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/properties/clusters?${qs}`).then((r) => r.json());
};

export const getProperty = (id: number | string) =>
  request(`/api/properties/${id}`).then((r) => r.json());

export const updateProperty = (id: number | string, data: Record<string, unknown>) =>
  request(`/api/properties/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  }).then((r) => r.json());

export const deleteProperty = (id: number | string) =>
  request(`/api/properties/${id}`, { method: "DELETE" }).then((r) => r.json());

export const batchUpdateProperties = (propertyIds: number[], finding: string, notes = "") =>
  request("/api/properties/batch-update", {
    method: "POST",
    body: JSON.stringify({ property_ids: propertyIds, finding, notes }),
  }).then((r) => r.json());

export const importCSV = async (file: File) => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/properties/import", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await getErrorMessage(res, "Import failed"));
  return res.json();
};

export const importCSVText = async (text: string) => {
  const formData = new FormData();
  formData.append("text", text);
  const res = await fetch("/api/properties/import", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await getErrorMessage(res, "Import failed"));
  return res.json();
};

export const getStats = () =>
  request("/api/properties/stats/summary").then((r) => r.json());

// Imagery
export const getImageryStatus = () =>
  request("/api/imagery/status").then((r) => r.json());

export const geocodeBatch = (limit = 50) =>
  request(`/api/imagery/geocode-batch?limit=${limit}`, { method: "POST" }).then((r) => r.json());

export const fetchImageryBatch = (limit = 25) =>
  request(`/api/imagery/fetch-batch?limit=${limit}`, { method: "POST" }).then((r) => r.json());

export const fetchHistoricalImagery = (propertyId: number | string) =>
  request(`/api/imagery/fetch-historical/${propertyId}`, { method: "POST" }).then((r) => r.json());

export const getImageUrl = (propertyId: number | string, type: string) =>
  `/api/imagery/image/${propertyId}/${type}`;

// Detection
export const runDetectionBatch = (limit = 50) =>
  request(`/api/detection/analyze-batch?limit=${limit}`, { method: "POST" }).then((r) => r.json());

export const getDetectionSummary = () =>
  request("/api/detection/summary").then((r) => r.json());

// Pipeline (one-button processing)
export const runPipeline = ({ limit = 25, processAll = false } = {}) => {
  const qs = new URLSearchParams({
    limit: String(limit),
    process_all: processAll ? "true" : "false",
  }).toString();
  return request(`/api/pipeline/process?${qs}`, { method: "POST" }).then((r) => r.json());
};

// Pipeline with SSE progress streaming
export const runPipelineStream = (
  limit = 25,
  onEvent: (event: Record<string, unknown>) => void,
  { processAll = false } = {},
) => {
  const controller = new AbortController();
  const qs = new URLSearchParams({
    limit: String(limit),
    process_all: processAll ? "true" : "false",
  }).toString();
  const run = async () => {
    const res = await fetch(`/api/pipeline/process-stream?${qs}`, {
      method: "POST",
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`Pipeline error: ${res.status}`);
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop()!;
      for (const chunk of lines) {
        const dataLine = chunk.trim();
        if (dataLine.startsWith("data: ")) {
          try {
            const event = JSON.parse(dataLine.slice(6));
            onEvent(event);
          } catch {
            /* skip malformed */
          }
        }
      }
    }
  };
  return { promise: run(), cancel: () => controller.abort() };
};

// Pipeline: process ALL remaining properties with auto-continue
export const runPipelineAll = (
  batchSize = 100,
  onEvent: (event: Record<string, unknown>) => void,
) => {
  const controller = new AbortController();
  const run = async () => {
    const res = await fetch(`/api/pipeline/process-all?batch_size=${batchSize}`, {
      method: "POST",
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`Pipeline error: ${res.status}`);
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop()!;
      for (const chunk of lines) {
        const dataLine = chunk.trim();
        if (dataLine.startsWith("data: ")) {
          try {
            const event = JSON.parse(dataLine.slice(6));
            onEvent(event);
          } catch {
            /* skip malformed */
          }
        }
      }
    }
  };
  return { promise: run(), cancel: () => controller.abort() };
};

// Communications
export const getComms = (propertyId: number | string) =>
  request(`/api/communications/${propertyId}`).then((r) => r.json());

export const createComm = (data: Record<string, unknown>) =>
  request("/api/communications/", {
    method: "POST",
    body: JSON.stringify(data),
  }).then((r) => r.json());

// Export URLs
export const exportCSVUrl = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return `/api/properties/export/csv?${qs}`;
};

export const exportInspectionListUrl = () => "/api/properties/export/inspection-list";
export const exportResolvedCsvUrl = () => "/api/properties/export/resolved";
export const exportSummaryUrl = () => "/api/properties/export/summary";
