import type {
  DocumentListResponse,
  DocumentResponse,
  DocumentUploadFields,
  SearchHistoryResponse,
  SearchResponse,
} from "./types";

// Same-origin by default: nginx (prod) / Vite (dev) proxy /api → backend.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  apiKey: string,
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: { ...options.headers, "X-API-Key": apiKey },
  });

  if (!response.ok) {
    let detail = `Error ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // response body was not JSON; keep the generic message
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function buildDocumentQuery(filters: {
  name?: string;
  status?: string;
  limit: number;
  offset: number;
}): string {
  const params = new URLSearchParams();
  if (filters.name) params.set("name", filters.name);
  if (filters.status) params.set("status", filters.status);
  params.set("limit", String(filters.limit));
  params.set("offset", String(filters.offset));
  return params.toString();
}

export const api = {
  // Validates a key by hitting an authenticated endpoint.
  async verifyKey(apiKey: string): Promise<void> {
    await request<DocumentListResponse>(apiKey, "/documents?limit=1&offset=0");
  },

  listDocuments(
    apiKey: string,
    filters: { name?: string; status?: string; limit: number; offset: number },
  ): Promise<DocumentListResponse> {
    return request<DocumentListResponse>(
      apiKey,
      `/documents?${buildDocumentQuery(filters)}`,
    );
  },

  // Returns the document plus isDuplicate: the backend answers 200 when the
  // same content already exists (deduplicated, not re-processed) and 202 when
  // a new document was accepted for ingestion.
  async uploadDocument(
    apiKey: string,
    file: File,
    fields: DocumentUploadFields,
    cover: File | null,
  ): Promise<{ document: DocumentResponse; isDuplicate: boolean }> {
    const form = new FormData();
    form.append("file", file);
    for (const [key, value] of Object.entries(fields)) {
      if (value) form.append(key, value);
    }
    if (cover) form.append("cover_image", cover);

    const response = await fetch(`${BASE_URL}/documents`, {
      method: "POST",
      headers: { "X-API-Key": apiKey },
      body: form,
    });
    if (!response.ok) {
      let detail = `Error ${response.status}`;
      try {
        const body = await response.json();
        if (body?.detail) detail = String(body.detail);
      } catch {
        // response body was not JSON; keep the generic message
      }
      throw new ApiError(response.status, detail);
    }
    const document = (await response.json()) as DocumentResponse;
    return { document, isDuplicate: response.status === 200 };
  },

  deleteDocument(apiKey: string, name: string): Promise<void> {
    return request<void>(apiKey, `/documents/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
  },

  // Downloads through the same API-key-authenticated path the search returns.
  // A plain <a href> can't send the X-API-Key header, so we fetch the blob.
  async downloadDocument(apiKey: string, downloadUrl: string): Promise<Blob> {
    const response = await fetch(`${BASE_URL}${downloadUrl}`, {
      headers: { "X-API-Key": apiKey },
    });
    if (!response.ok) {
      throw new ApiError(response.status, `Error ${response.status} al descargar`);
    }
    return response.blob();
  },

  search(apiKey: string, query: string): Promise<SearchResponse> {
    return request<SearchResponse>(apiKey, "/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
  },

  searchHistory(
    apiKey: string,
    filters: { from_date?: string; to_date?: string; limit: number; offset: number },
  ): Promise<SearchHistoryResponse> {
    const params = new URLSearchParams();
    if (filters.from_date) params.set("from_date", filters.from_date);
    if (filters.to_date) params.set("to_date", filters.to_date);
    params.set("limit", String(filters.limit));
    params.set("offset", String(filters.offset));
    return request<SearchHistoryResponse>(apiKey, `/search/history?${params.toString()}`);
  },
};
