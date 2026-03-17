import { UploadedFile } from "@/types";

export default function FileChip({
  file,
  onRemove,
}: {
  file: UploadedFile;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="flex items-center gap-1 bg-violet-500/20 border border-violet-500/40 text-violet-300 text-xs px-3 py-1 rounded-full">
      <span>📄 {file.file_name}</span>
      <button
        onClick={() => onRemove(file.file_id)}
        className="ml-1 hover:text-red-400 transition-colors"
      >
        ✕
      </button>
    </div>
  );
}
