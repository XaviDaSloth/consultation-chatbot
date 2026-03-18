import { Message } from "@/types";
import CitationCard from "./CitationCard";

export default function ChatWindow({ messages }: { messages: any[] }) {
  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[75%] rounded-xl p-4 ${
              msg.role === "user"
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-100"
            }`}
          >
            {msg.role === "user" ? (
              <p>{msg.content}</p>
            ) : (
              <AIMessage message={msg} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function AIMessage({ message }: { message: any }) {
  const content = message.content;

  // Case 1 — currently streaming (plain string, cursor visible)
  if (message.isStreaming) {
    return (
      <p>
        {content}
        <span className="inline-block w-2 h-4 bg-violet-400 ml-1 animate-pulse" />
      </p>
    );
  }

  // Case 2 — plain string (saved by streaming endpoint)
  if (typeof content === "string") {
    return <p>{content}</p>;
  }

  // Case 3 — structured object (saved by old /conversation endpoint)
  if (typeof content === "object" && content !== null) {
    // Handles both { direct_answer } and any other object shape
    const answer = content.direct_answer || JSON.stringify(content);
    return (
      <>
        <p>{answer}</p>
        {content.supporting_and_evidence?.length > 0 && (
          <CitationCard evidence={content.supporting_and_evidence} />
        )}
      </>
    );
  }

  // Fallback
  return <p className="text-gray-500 italic">Unable to display message.</p>;
}
