const BASE = "";  // Vite proxy handles /api routing

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res;
}

// Properties
export const getProperties = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return request(`/api/properties/?${qs}`).then(r => r.json());
};

export const getProperty = (id) =>
  request(`/api/properties/${id}`).then(r => r.json());

export const updateProperty = (id, data) =>
  request(`/api/properties/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  }).then(r => r.json());

export const deleteProperty = (id) =>
  request(`/api/properties/${id}`, { method: "DELETE" }).then(r => r.json());

export const importCSV = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/properties/import", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Import failed");
  return res.json();
};

export const importCSVText = async (text) => {
  const formData = new FormData();
  formData.append("text", text);
  const res = await fetch("/api/properties/import", {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error("Import failed");
  return res.json();
};

export const getStats = () =>
  request("/api/properties/stats/summary").then(r => r.json());

// Imagery
export const getImageryStatus = () =>
  request("/api/imagery/status").then(r => r.json());

export const geocodeBatch = (limit = 50) =>
  request(`/api/imagery/geocode-batch?limit=${limit}`, { method: "POST" }).then(r => r.json());

export const fetchImageryBatch = (limit = 25) =>
  request(`/api/imagery/fetch-batch?limit=${limit}`, { method: "POST" }).then(r => r.json());

export const getImageUrl = (propertyId, type) =>
  `/api/imagery/image/${propertyId}/${type}`;

// Detection
export const runDetectionBatch = (limit = 50) =>
  request(`/api/detection/analyze-batch?limit=${limit}`, { method: "POST" }).then(r => r.json());

export const getDetectionSummary = () =>
  request("/api/detection/summary").then(r => r.json());

// Pipeline (one-button processing)
export const runPipeline = (limit = 25) =>
  request(`/api/pipeline/process?limit=${limit}`, { method: "POST" }).then(r => r.json());

// Pipeline with SSE progress streaming
export const runPipelineStream = (limit = 25, onEvent) => {
  const controller = new AbortController();
  const run = async () => {
    const res = await fetch(`/api/pipeline/process-stream?limit=${limit}`, {
      method: "POST",
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`Pipeline error: ${res.status}`);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop();
      for (const chunk of lines) {
        const dataLine = chunk.trim();
        if (dataLine.startsWith("data: ")) {
          try {
            const event = JSON.parse(dataLine.slice(6));
            onEvent(event);
          } catch { /* skip malformed */ }
        }
      }
    }
  };
  return { promise: run(), cancel: () => controller.abort() };
};

// Communications
export const getComms = (propertyId) =>
  request(`/api/communications/${propertyId}`).then(r => r.json());

export const createComm = (data) =>
  request("/api/communications/", {
    method: "POST",
    body: JSON.stringify(data),
  }).then(r => r.json());

// Export
export const exportCSVUrl = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return `/api/properties/export/csv?${qs}`;
};

export const exportInspectionListUrl = () =>
  "/api/properties/export/inspection-list";

export const exportSummaryUrl = () =>
  "/api/properties/export/summary";
