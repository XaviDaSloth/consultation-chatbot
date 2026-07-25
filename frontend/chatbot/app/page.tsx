"use client";

import { useEffect, useRef, useState } from "react";
import ChatWindow from "./components/ChatWindow";
import FileChip from "./components/FileChip";
import FileUploader from "./components/FileUploader";
import Sidebar from "./components/Sidebar";
import { getApiUrl } from "@/lib/api";
import { Message, UploadedFile } from "@/types";

type SessionFile = { id: string; doc_name: string };
type SessionMessage = { message_source: "user" | "ai"; content: string };
type StreamEvent =
  | { type: "session"; session_id: string }
  | { type: "token"; value: string }
  | { type: "structured"; data: Message["content"] }
  | { type: "done" };

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionFileIds, setSessionFileIds] = useState<string[]>([]);
  const [sessionFiles, setSessionFiles] = useState<SessionFile[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const canChat = uploadedFiles.length > 0 || sessionId !== null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleNewChat() {
    setSessionId(null);
    setMessages([]);
    setUploadedFiles([]);
    setSessionFiles([]);
    setSessionFileIds([]);
    setInput("");
  }

  async function handleSelectSession(id: string) {
    setSessionId(id);
    setUploadedFiles([]);
    setSessionLoading(true);

    const [messagesRes, filesRes] = await Promise.all([
      fetch(getApiUrl(`/sessions/${id}/messages`)),
      fetch(getApiUrl(`/sessions/${id}/files`)),
    ]);

    const messagesData = (await messagesRes.json()) as SessionMessage[];
    const filesData = (await filesRes.json()) as SessionFile[];

    setSessionFiles(filesData);
    setSessionFileIds(filesData.map((f) => f.id));

    const formatted: Message[] = [...messagesData].reverse().map((msg) => {
      if (msg.message_source === "user") {
        return { role: "user", content: msg.content };
      }

      let content: Message["content"];
      try {
        content = JSON.parse(msg.content);
      } catch {
        content = msg.content;
      }

      return { role: "ai", content };
    });

    setMessages(formatted);
    setSessionLoading(false);
  }

  async function createSession() {
    const res = await fetch(getApiUrl("/conversation/init"), {
      method: "POST",
    });
    const data = await res.json();
    return data.session_id as string;
  }

  async function handleFileReady(file: UploadedFile) {
    setUploadedFiles((prev) => [...prev, file]);
    setSessionFileIds((prev) => [...prev, file.file_id]);
  }

  function handleRemoveFile(fileId: string) {
    setUploadedFiles((prev) => prev.filter((f) => f.file_id !== fileId));
    setSessionFileIds((prev) => prev.filter((id) => id !== fileId));
  }

  async function ensureSession(): Promise<string> {
    if (sessionId) return sessionId;

    const newId = await createSession();
    setSessionId(newId);
    setSessionFiles([]);
    setSessionFileIds([]);
    return newId;
  }

  async function sendMessage() {
    if (!input.trim() || !canChat || loading) return;

    const userQuery = input;
    const fileIds =
      uploadedFiles.length > 0
        ? uploadedFiles.map((f) => f.file_id)
        : sessionFileIds;

    setMessages((prev) => [
      ...prev,
      { role: "user", content: userQuery },
      { role: "ai", content: "", isStreaming: true },
    ]);
    setInput("");
    setLoading(true);

    const res = await fetch(getApiUrl("/conversation/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file_ids: fileIds,
        user_query: userQuery,
        session_id: sessionId,
      }),
    });

    const reader = res.body?.getReader();
    if (!reader) {
      setLoading(false);
      return;
    }

    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split("\n").filter((l) => l.startsWith("data: "));

      for (const line of lines) {
        const json = JSON.parse(line.replace("data: ", "")) as StreamEvent;

        if (json.type === "session" && !sessionId) {
          setSessionId(json.session_id);
        }

        if (json.type === "token") {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];

            return [
              ...updated.slice(0, -1),
              { ...last, content: (last.content as string) + json.value },
            ];
          });
        }

        if (json.type === "structured") {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];

            return [
              ...updated.slice(0, -1),
              { ...last, content: json.data, isStreaming: false },
            ];
          });
        }

        if (json.type === "done") {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];

            return [...updated.slice(0, -1), { ...last, isStreaming: false }];
          });
          setLoading(false);
        }
      }
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-950 text-white">
      <Sidebar
        activeSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
      />

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="border-b border-gray-800 bg-gray-950/95 px-5 py-4">
          <FileUploader
            onFileReady={handleFileReady}
            onBeforeUpload={ensureSession}
          />

          {uploadedFiles.length > 0 && (
            <div className="mt-3 space-y-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                Active files
              </p>
              <div className="flex flex-wrap gap-2">
                {uploadedFiles.map((f) => (
                  <FileChip
                    key={f.file_id}
                    file={f}
                    onRemove={handleRemoveFile}
                  />
                ))}
              </div>
            </div>
          )}

          {sessionId &&
            uploadedFiles.length === 0 &&
            sessionFileIds.length > 0 && (
              <div className="mt-3 space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                  Files in this session
                </p>
                <div className="flex flex-wrap gap-2">
                  {sessionFiles.map((f) => (
                    <span
                      key={f.id}
                      className="rounded-md border border-gray-800 bg-gray-900 px-2.5 py-1.5 text-xs text-gray-300"
                    >
                      {f.doc_name}
                    </span>
                  ))}
                </div>
              </div>
            )}
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-950">
          {sessionLoading ? (
            <div className="flex h-full flex-col items-center justify-center text-gray-500">
              <div className="mb-3 h-8 w-8 rounded-full border-2 border-teal-500 border-t-transparent animate-spin" />
              <p className="text-sm">Loading session...</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center px-6 text-center">
              <div className="max-w-sm">
                <p className="text-lg font-medium text-gray-200">
                  Upload a PDF to start
                </p>
                <p className="mt-2 text-sm leading-6 text-gray-500">
                  Ask questions, compare sections, and pull cited answers from
                  your documents.
                </p>
              </div>
            </div>
          ) : (
            <ChatWindow messages={messages} />
          )}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-gray-800 bg-gray-950 px-5 py-4">
          {!canChat && (
            <p className="mb-2 text-center text-xs text-gray-600">
              Upload at least one PDF to start chatting
            </p>
          )}
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-lg border border-gray-800 bg-gray-900 px-4 py-3 text-sm outline-none transition-colors placeholder-gray-600 focus:border-teal-500"
              placeholder={
                canChat
                  ? "Ask something about your PDFs..."
                  : "Upload a file first..."
              }
              value={input}
              disabled={!canChat || loading}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            />
            <button
              type="button"
              onClick={sendMessage}
              disabled={!canChat || loading}
              className="rounded-lg bg-teal-600 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? "Sending" : "Send"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
