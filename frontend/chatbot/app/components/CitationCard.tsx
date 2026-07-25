import { CitationEvidence } from "@/types";

export default function CitationCard({
  evidence,
}: {
  evidence: CitationEvidence[];
}) {
  if (!evidence.length) return null;

  return (
    <div className="space-y-2 border-t border-gray-800 pt-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
        Sources
      </p>
      <div className="space-y-2">
        {evidence.map((item, i) => (
          <div
            key={i}
            className="rounded-md border border-gray-800 bg-gray-950/60 px-3 py-2 text-xs text-gray-300"
          >
            <p className="leading-5 text-gray-200">
              &quot;{item.extracted_specific_citation}&quot;
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
              {item.doc_name && (
                <span className="max-w-full truncate rounded bg-gray-800 px-2 py-0.5 text-gray-300">
                  {item.doc_name}
                </span>
              )}
              <span>Page {item.page_no}</span>
              <span>Chunk {item.chunk_id}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
