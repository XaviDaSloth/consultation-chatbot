"use client";
import { useState, useRef } from "react";
import { UploadedFile } from "@/types";

interface Props {
  onFileReady: (file: UploadedFile) => void;
  sessionId: string | null; // 👈 add this
}

export default function FileUploader({ onFileReady, sessionId }: Props) {
  const [status, setStatus] = useState<"idle" | "uploading" | "processing">(
    "idle",
  );
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function processFile(file: File) {
    if (!file || file.type !== "application/pdf") return;
    setStatus("uploading");

    const formData = new FormData();
    formData.append("file", file);

    // sessionId is now guaranteed to exist before upload
    const uploadUrl = sessionId
      ? `${process.env.NEXT_PUBLIC_API_URL}/uploadfile?session_id=${sessionId}`
      : `${process.env.NEXT_PUBLIC_API_URL}/uploadfile`;

    const uploadRes = await fetch(uploadUrl, {
      method: "POST",
      body: formData,
    });
    const { file_id } = await uploadRes.json();

    setStatus("processing");
    await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/process_file?file_id=${file_id}`,
      {
        method: "POST",
      },
    );

    setStatus("idle");
    onFileReady({ file_id, file_name: file.name });
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    processFile(file);
  }

  return (
    <div
      onClick={() => status === "idle" && inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`
        relative border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-200
        ${dragging ? "border-violet-400 bg-violet-500/10" : "border-gray-600 hover:border-violet-500 hover:bg-violet-500/5"}
        ${status !== "idle" ? "pointer-events-none opacity-70" : ""}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => e.target.files?.[0] && processFile(e.target.files[0])}
      />

      {status === "idle" && (
        <>
          <div className="text-3xl mb-2">📂</div>
          <p className="text-sm text-gray-300">
            Drop a PDF here or{" "}
            <span className="text-violet-400 font-medium">browse</span>
          </p>
          <p className="text-xs text-gray-500 mt-1">
            You can add multiple files
          </p>
        </>
      )}
      {status === "uploading" && (
        <p className="text-yellow-400 text-sm animate-pulse">⬆ Uploading...</p>
      )}
      {status === "processing" && (
        <p className="text-blue-400 text-sm animate-pulse">
          ⚙ Processing embeddings...
        </p>
      )}
    </div>
  );
}
