export interface CitationEvidence {
  extracted_specific_citation: string;
  chunk_id: string;
  page_no: number;
  doc_name?: string; 
}
export interface AIResponse {
  direct_answer: string;
  supporting_and_evidence: CitationEvidence[];
}

export interface Message {
  role: "user" | "ai";
  content: string | AIResponse;
  isStreaming?: boolean;
}

export interface Session {
  id: string;
  created_at: string;
  firstMessage?: string;
}

export interface UploadedFile {
  file_id: string;
  file_name: string;
}

export interface StreamingMessage {
  role: "ai";
  content: string;
  isStreaming: boolean;
}
