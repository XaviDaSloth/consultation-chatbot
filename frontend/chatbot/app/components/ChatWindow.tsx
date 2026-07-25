import { Message } from "@/types";
import CitationCard from "./CitationCard";

export default function ChatWindow({ messages }: { messages: Message[] }) {
  return (
    <div className="flex h-full flex-col gap-5 overflow-y-auto px-6 py-5">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[min(760px,82%)] rounded-lg px-4 py-3 text-sm leading-6 shadow-sm ${
              msg.role === "user"
                ? "bg-teal-600 text-white"
                : "border border-gray-800 bg-gray-900 text-gray-100"
            }`}
          >
            {msg.role === "user" ? (
              <p className="whitespace-pre-wrap">{msg.content as string}</p>
            ) : (
              <AIMessage message={msg} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function AIMessage({ message }: { message: Message }) {
  const content = message.content;

  if (message.isStreaming) {
    return (
      <p className="whitespace-pre-wrap">
        {content as string}
        <span className="ml-1 inline-block h-4 w-1.5 translate-y-0.5 rounded-full bg-teal-300 animate-pulse" />
      </p>
    );
  }

  if (typeof content === "string") {
    return <p className="whitespace-pre-wrap">{content}</p>;
  }

  if (typeof content === "object" && content !== null) {
    const answer = content.direct_answer || JSON.stringify(content);
    return (
      <div className="space-y-3">
        <p className="whitespace-pre-wrap">{answer}</p>
        <CitationCard evidence={content.supporting_and_evidence ?? []} />
      </div>
    );
  }

  return <p className="text-gray-500 italic">Unable to display message.</p>;
}
