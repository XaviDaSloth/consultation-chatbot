"use client";
import { useState, useRef, useEffect } from "react";
import Sidebar from "./components/Sidebar";
import FileUploader from "./components/FileUploader";
import FileChip from "./components/FileChip";
import ChatWindow from "./components/ChatWindow";
import { Message, UploadedFile } from "@/types";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionFileIds, setSessionFileIds] = useState<string[]>([]);
  const [sessionFiles, setSessionFiles] = useState<
    { id: string; doc_name: string }[]
  >([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [sessionLoading, setSessionLoading] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleNewChat() {
    setSessionId(null);
    setMessages([]);
    setUploadedFiles([]);
    setInput("");
  }

  async function handleSelectSession(id: string) {
    setSessionId(id);
    setUploadedFiles([]);
    setSessionLoading(true);

    // Fetch messages and files in parallel
    const [messagesRes, filesRes] = await Promise.all([
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/sessions/${id}/messages`),
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/sessions/${id}/files`), // 👈 add this
    ]);

    const messagesData = await messagesRes.json();
    const filesData = await filesRes.json();

    console.log("files for session:", filesData); // temporary — check what comes back

    // Populate sessionFileIds for sending with chat messages
    setSessionFiles(filesData);
    setSessionFileIds(filesData.map((f: any) => f.id));

    const reversed = [...messagesData].reverse();
    const formatted: Message[] = reversed.map((msg: any) => {
      if (msg.message_source === "user") {
        return { role: "user", content: msg.content };
      }
      let content;
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
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/conversation/init`,
      {
        method: "POST",
      },
    );
    const data = await res.json();
    return data.session_id;
  }

  async function handleFileReady(file: UploadedFile) {
    let currentSessionId = sessionId;

    if (!currentSessionId) {
      currentSessionId = await createSession();
      setSessionId(currentSessionId);
    }

    setUploadedFiles((prev) => [...prev, file]);
    setSessionFileIds((prev) => [...prev, file.file_id]); // 👈 keep in sync
  }

  function handleRemoveFile(fileId: string) {
    setUploadedFiles((prev) => prev.filter((f) => f.file_id !== fileId));
  }

  async function sendMessage() {
    if (!input.trim() || !canChat) return;

    const fileIds =
      uploadedFiles.length > 0
        ? uploadedFiles.map((f) => f.file_id)
        : sessionFileIds;

    console.log("=== SENDING MESSAGE ===");
    console.log("sessionId:", sessionId);
    console.log("uploadedFiles:", uploadedFiles);
    console.log("sessionFileIds:", sessionFileIds);
    console.log("fileIds being sent:", fileIds);
    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    // Add an empty AI message that we'll fill in as tokens arrive
    setMessages((prev) => [
      ...prev,
      { role: "ai", content: "", isStreaming: true },
    ]);

    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/conversation/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_ids: fileIds,
          user_query: input,
          session_id: sessionId,
        }),
      },
    );

    // Read the stream
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split("\n").filter((l) => l.startsWith("data: "));

      for (const line of lines) {
        const json = JSON.parse(line.replace("data: ", ""));

        if (json.type === "session" && !sessionId) {
          setSessionId(json.session_id);
        }

        if (json.type === "token") {
          // Append each token to the last message
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
          // Replace the streamed plain text with the full structured response
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
          // Mark streaming as finished
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

  const canChat = uploadedFiles.length > 0 || sessionId !== null;

  return (
    <div className="flex h-screen bg-gray-900 text-white overflow-hidden">
      <Sidebar
        activeSessionId={sessionId}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
      />

      <main className="flex flex-col flex-1 overflow-hidden">
        {/* File area */}
        <div className="p-4 border-b border-gray-800 space-y-3">
          <FileUploader onFileReady={handleFileReady} sessionId={sessionId} />
          {uploadedFiles.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs text-gray-500 uppercase tracking-wide">
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

          {/* Show session files when loading a past session with no new uploads */}
          {sessionId &&
            uploadedFiles.length === 0 &&
            sessionFileIds.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs text-gray-500 uppercase tracking-wide">
                  Files in this session
                </p>
                <div className="flex flex-wrap gap-2">
                  {sessionFiles.map((f) => (
                    <span
                      key={f.id}
                      className="text-xs bg-violet-500/20 text-violet-400 border border-violet-500/30 px-3 py-1 rounded-full"
                    >
                      📄 {f.doc_name}
                    </span>
                  ))}
                </div>
              </div>
            )}
        </div>

        {/* Chat area */}
        <div className="flex-1 overflow-y-auto">
          {sessionLoading ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Loading session...</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-600">
              <p className="text-4xl mb-3">💬</p>
              <p className="text-sm">Upload a PDF and start asking questions</p>
            </div>
          ) : (
            <ChatWindow messages={messages} />
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div className="p-4 border-t border-gray-800">
          {!canChat && (
            <p className="text-xs text-center text-gray-600 mb-2">
              Upload at least one PDF to start chatting
            </p>
          )}
          <div className="flex gap-2">
            <input
              className="flex-1 bg-gray-800 border border-gray-700 focus:border-violet-500 rounded-xl px-4 py-3 text-sm outline-none transition-colors placeholder-gray-500"
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
              onClick={sendMessage}
              disabled={!canChat || loading}
              className="bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors px-5 py-3 rounded-xl text-sm font-medium"
            >
              {loading ? "..." : "Send"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
