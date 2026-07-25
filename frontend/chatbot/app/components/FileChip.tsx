import { UploadedFile } from "@/types";

export default function FileChip({
  file,
  onRemove,
}: {
  file: UploadedFile;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="flex max-w-full items-center gap-2 rounded-md border border-teal-500/30 bg-teal-500/10 px-2.5 py-1.5 text-xs text-teal-100">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-teal-300" />
      <span className="truncate">{file.file_name}</span>
      <button
        type="button"
        onClick={() => onRemove(file.file_id)}
        aria-label={`Remove ${file.file_name}`}
        className="ml-1 rounded px-1 text-teal-300 transition-colors hover:bg-red-500/10 hover:text-red-300"
      >
        x
      </button>
    </div>
  );
}
