import type {
  AnswerPromptResponse,
  DocumentListResponse,
  DocumentResponse,
  DocumentUploadFields,
  SearchHistoryResponse,
  SearchResponse,
  SearchScopeResponse,
  UploadBatchResponse,
  UploadHistoryResponse,
} from "./types";

// Same-origin by default: nginx (prod) / Vite (dev) proxy /api → backend.
export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

// Downloads and covers are public endpoints (no X-API-Key), so plain
// hrefs/img-srcs work — no blob fetching needed.
export function downloadHref(downloadUrl: string): string {
  return `${BASE_URL}${downloadUrl}`;
}

export function coverHref(name: string): string {
  return `${BASE_URL}/documents/${encodeURIComponent(name)}/cover`;
}

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

  // Multi-file upload: every file travels in one request and the backend
  // registers them in parallel. Per-file outcomes come back in items[]
  // (processing | skipped_duplicate | failed).
  uploadDocuments(
    apiKey: string,
    files: File[],
    fields: DocumentUploadFields,
    cover: File | null,
  ): Promise<UploadBatchResponse> {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    for (const [key, value] of Object.entries(fields)) {
      if (value) form.append(key, value);
    }
    if (cover) form.append("cover_image", cover);
    return request<UploadBatchResponse>(apiKey, "/documents", {
      method: "POST",
      body: form,
    });
  },

  uploadHistory(
    apiKey: string,
    filters: { outcome?: string; limit: number; offset: number },
  ): Promise<UploadHistoryResponse> {
    const params = new URLSearchParams();
    if (filters.outcome) params.set("outcome", filters.outcome);
    params.set("limit", String(filters.limit));
    params.set("offset", String(filters.offset));
    return request<UploadHistoryResponse>(apiKey, `/uploads?${params.toString()}`);
  },

  getSearchScope(apiKey: string): Promise<SearchScopeResponse> {
    return request<SearchScopeResponse>(apiKey, "/settings/search-scope");
  },

  updateSearchScope(apiKey: string, prompt: string): Promise<SearchScopeResponse> {
    return request<SearchScopeResponse>(apiKey, "/settings/search-scope", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
  },

  getAnswerPrompt(apiKey: string): Promise<AnswerPromptResponse> {
    return request<AnswerPromptResponse>(apiKey, "/settings/answer-prompt");
  },

  // An empty prompt resets to the built-in default template.
  updateAnswerPrompt(apiKey: string, prompt: string): Promise<AnswerPromptResponse> {
    return request<AnswerPromptResponse>(apiKey, "/settings/answer-prompt", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });
  },

  getDocument(apiKey: string, name: string): Promise<DocumentResponse> {
    return request<DocumentResponse>(apiKey, `/documents/${encodeURIComponent(name)}`);
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

  // The cover endpoint also needs the X-API-Key header, so it is fetched as a
  // blob and turned into an object URL by the caller.
  async downloadCover(apiKey: string, name: string): Promise<Blob> {
    const response = await fetch(
      `${BASE_URL}/documents/${encodeURIComponent(name)}/cover`,
      { headers: { "X-API-Key": apiKey } },
    );
    if (!response.ok) {
      throw new ApiError(response.status, `Error ${response.status} al cargar la portada`);
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
