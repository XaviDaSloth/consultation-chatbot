"use client";

import { useRef, useState } from "react";
import { getApiUrl } from "@/lib/api";
import { UploadedFile } from "@/types";

interface Props {
  onFileReady: (file: UploadedFile) => void;
  onBeforeUpload: () => Promise<string>;
}

export default function FileUploader({ onFileReady, onBeforeUpload }: Props) {
  const [status, setStatus] = useState<"idle" | "uploading" | "processing">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function processFile(file: File) {
    if (!file || file.type !== "application/pdf") {
      setError("Please choose a PDF file.");
      return;
    }

    setStatus("uploading");
    setError(null);

    try {
      const currentSessionId = await onBeforeUpload();
      const formData = new FormData();
      formData.append("file", file);

      const uploadRes = await fetch(
        getApiUrl(
          `/uploadfile?session_id=${encodeURIComponent(currentSessionId)}`,
        ),
        {
          method: "POST",
          body: formData,
        },
      );

      if (!uploadRes.ok) {
        throw new Error(`Upload failed with status ${uploadRes.status}`);
      }

      const { file_id } = await uploadRes.json();

      if (!file_id) {
        throw new Error("Upload response did not include a file id");
      }

      setStatus("processing");

      const processRes = await fetch(
        getApiUrl(`/process_file?file_id=${encodeURIComponent(file_id)}`),
        { method: "POST" },
      );

      if (!processRes.ok) {
        throw new Error(`Processing failed with status ${processRes.status}`);
      }

      setStatus("idle");
      onFileReady({ file_id, file_name: file.name });
    } catch (err) {
      console.error(err);
      setStatus("idle");
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    processFile(e.dataTransfer.files[0]);
  }

  const isBusy = status !== "idle";

  return (
    <div className="space-y-2">
      <div
        onClick={() => !isBusy && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          if (!isBusy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`group flex min-h-16 items-center justify-between gap-4 rounded-lg border px-4 py-3 transition-colors ${
          isBusy ? "cursor-default opacity-80" : "cursor-pointer"
        } ${
          dragging
            ? "border-teal-400 bg-teal-400/10"
            : "border-gray-800 bg-gray-900/70 hover:border-gray-700 hover:bg-gray-900"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) =>
            e.target.files?.[0] && processFile(e.target.files[0])
          }
        />

        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-100">
            {status === "idle" && "Drop PDF files here"}
            {status === "uploading" && "Uploading PDF"}
            {status === "processing" && "Indexing document"}
          </p>
          <p className="mt-0.5 text-xs text-gray-500">
            {status === "idle"
              ? "Browse or drag a file to add it to this chat."
              : "Keep this tab open while the document is prepared."}
          </p>
        </div>

        {isBusy ? (
          <span className="block h-5 w-5 shrink-0 rounded-full border-2 border-teal-400 border-t-transparent animate-spin" />
        ) : (
          <span className="shrink-0 rounded-md border border-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300 transition-colors group-hover:border-teal-500 group-hover:text-teal-300">
            Browse
          </span>
        )}
      </div>

      {error && <p className="text-sm text-red-300">{error}</p>}
    </div>
  );
}
