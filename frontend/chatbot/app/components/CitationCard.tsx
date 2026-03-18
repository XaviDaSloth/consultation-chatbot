import { CitationEvidence } from "@/types";

export default function CitationCard({
  evidence,
}: {
  evidence: CitationEvidence[];
}) {
  if (!evidence.length) return null;

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
        Sources
      </p>
      {evidence.map((item, i) => (
        <div
          key={i}
          className="border-l-4 border-violet-400 pl-3 text-sm text-gray-300"
        >
          <p className="italic">"{item.extracted_specific_citation}"</p>
          <div className="flex flex-wrap gap-2 mt-1">
            {item.doc_name && (
              <span className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded-full">
                📄 {item.doc_name}
              </span>
            )}
            <span className="text-xs bg-violet-500/20 text-violet-400 px-2 py-0.5 rounded-full">
              Page {item.page_no}
            </span>
            <span className="text-xs text-gray-500">
              Chunk: {item.chunk_id}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
