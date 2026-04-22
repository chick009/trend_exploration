import type {
  AnalysisRunRequest,
  AnalysisRunStreamEvent,
  DbRowsQuery,
  DbRowsResponse,
  DbTableSchemaResponse,
  DbTablesResponse,
  IngestionRunRequest,
  KeywordSuggestionRequest,
  KeywordSuggestionResponse,
  PaginatedRunsResponse,
  RunStatusResponse,
  SourcesHealthResponse,
  TrendReport,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  suggestIngestionKeywords(payload: KeywordSuggestionRequest) {
    return request<KeywordSuggestionResponse>("/ingestion_runs/keyword_suggestions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  createIngestionRun(payload: IngestionRunRequest) {
    return request<RunStatusResponse>("/ingestion_runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  listIngestionRuns(limit = 20, offset = 0) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return request<PaginatedRunsResponse>(`/ingestion_runs?${params.toString()}`);
  },
  getIngestionRun(id: string) {
    return request<RunStatusResponse>(`/ingestion_runs/${id}`);
  },
  createAnalysisRun(payload: AnalysisRunRequest) {
    return request<RunStatusResponse>("/analysis_runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  async streamAnalysisRun(
    payload: AnalysisRunRequest,
    onEvent: (event: AnalysisRunStreamEvent) => void,
    signal?: AbortSignal,
  ) {
    const response = await fetch(`${API_BASE_URL}/analysis_runs/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || `Request failed with status ${response.status}`);
    }
    if (!response.body) {
      throw new Error("Streaming response body is unavailable.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const emitLine = (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }
      onEvent(JSON.parse(trimmed) as AnalysisRunStreamEvent);
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex >= 0) {
        emitLine(buffer.slice(0, newlineIndex));
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");
      }

      if (done) {
        break;
      }
    }

    emitLine(buffer);
  },
  listAnalysisRuns(limit = 20, offset = 0) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return request<PaginatedRunsResponse>(`/analysis_runs?${params.toString()}`);
  },
  getAnalysisRun(id: string) {
    return request<RunStatusResponse>(`/analysis_runs/${id}`);
  },
  getLatestTrends(market: string, category: string) {
    const params = new URLSearchParams({ market, category });
    return request<TrendReport>(`/trends/latest?${params.toString()}`);
  },
  getSourcesHealth() {
    return request<SourcesHealthResponse>("/sources/health");
  },
  listTables() {
    return request<DbTablesResponse>("/db/tables");
  },
  getTableSchema(name: string) {
    return request<DbTableSchemaResponse>(`/db/tables/${encodeURIComponent(name)}/schema`);
  },
  getTableRows(name: string, query: DbRowsQuery = {}) {
    const params = new URLSearchParams();
    if (query.limit != null) {
      params.set("limit", String(query.limit));
    }
    if (query.offset != null) {
      params.set("offset", String(query.offset));
    }
    if (query.search) {
      params.set("search", query.search);
    }
    if (query.column) {
      params.set("column", query.column);
    }
    if (query.order_by) {
      params.set("order_by", query.order_by);
    }
    if (query.order_dir) {
      params.set("order_dir", query.order_dir);
    }
    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return request<DbRowsResponse>(`/db/tables/${encodeURIComponent(name)}/rows${suffix}`);
  },
};
