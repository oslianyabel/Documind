export type DocumentStatus = "processing" | "ready" | "failed";

export interface DocumentResponse {
  id: string;
  name: string;
  original_filename: string;
  mime_type: string;
  sha256: string;
  size_bytes: number;
  status: DocumentStatus;
  page_count: number;
  chunk_count: number;
  summary: string | null;
  summary_generated: boolean;
  embedding_tokens_used: number;
  publication_year: number | null;
  author: string | null;
  description: string | null;
  category: string | null;
  language: string | null;
  has_cover_image: boolean;
  search_hit_count: number;
  created_at: string;
  download_url: string;
}

export interface DocumentListResponse {
  items: DocumentResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchChunkResult {
  document_name: string;
  start_page: number;
  start_line: number;
  end_page: number;
  end_line: number;
  text: string;
  similarity: number;
}

export interface SearchMetadata {
  embedding_tokens: number;
  total_time_ms: number;
}

export interface SearchResponse {
  chunks: SearchChunkResult[];
  documents: DocumentResponse[];
  answer: string | null;
  in_scope: boolean;
  metadata: SearchMetadata;
}

export interface SearchHistoryEntry {
  id: string;
  query_text: string;
  response: SearchResponse;
  embedding_tokens: number;
  duration_ms: number;
  passed_validation: boolean;
  created_at: string;
}

export interface SearchHistoryResponse {
  items: SearchHistoryEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentUploadFields {
  name?: string;
  publication_year?: string;
  author?: string;
  description?: string;
  category?: string;
  language?: string;
}

export type UploadOutcome = "processing" | "success" | "skipped_duplicate" | "failed";

export interface UploadItemResult {
  filename: string;
  outcome: UploadOutcome;
  detail: string | null;
  document: DocumentResponse | null;
}

export interface UploadBatchResponse {
  items: UploadItemResult[];
}

export interface UploadHistoryEntry {
  id: string;
  original_filename: string;
  document_name: string | null;
  sha256: string | null;
  outcome: UploadOutcome;
  error_traceback: string | null;
  document_id: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface UploadHistoryResponse {
  items: UploadHistoryEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface SearchScopeResponse {
  prompt: string | null;
}

export interface AnswerPromptResponse {
  prompt: string;
  is_default: boolean;
}
