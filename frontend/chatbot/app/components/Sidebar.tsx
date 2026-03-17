"use client";
import { useEffect, useState } from "react";
import { Session } from "@/types";

interface Props {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
}

export default function Sidebar({
  activeSessionId,
  onSelectSession,
  onNewChat,
}: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    async function fetchSessions() {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/sessions`);
      const data = await res.json();

      // Fetch first message for each session
      const withPreviews = await Promise.all(
        data.map(async (session: Session) => {
          const msgRes = await fetch(
            `${process.env.NEXT_PUBLIC_API_URL}/sessions/${session.id}/messages`,
          );
          const msgs = await msgRes.json();
          // messages are ordered desc, so last item is the first message
          const first = msgs[msgs.length - 1];
          return {
            ...session,
            firstMessage: first?.content?.slice(0, 40) || "New session",
          };
        }),
      );
      setSessions(withPreviews);
    }
    fetchSessions();
  }, [activeSessionId]); // refetch when active session changes (new chat created)

  return (
    <aside className="w-64 bg-gray-950 border-r border-gray-800 flex flex-col h-full">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold bg-gradient-to-r from-violet-400 to-pink-400 bg-clip-text text-transparent">
          PDF Chat
        </h1>
      </div>

      <div className="p-3">
        <button
          onClick={onNewChat}
          className="w-full bg-violet-600 hover:bg-violet-500 transition-colors text-white text-sm font-medium py-2 px-4 rounded-lg"
        >
          + New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 space-y-1">
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => onSelectSession(session.id)}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
              activeSessionId === session.id
                ? "bg-violet-600/30 text-violet-300 border border-violet-500/30"
                : "text-gray-400 hover:bg-gray-800 hover:text-gray-200"
            }`}
          >
            <p className="truncate">{session.firstMessage}</p>
            <p className="text-xs text-gray-600 mt-0.5">
              {new Date(session.created_at).toLocaleDateString()}
            </p>
          </button>
        ))}
      </div>
    </aside>
  );
}
