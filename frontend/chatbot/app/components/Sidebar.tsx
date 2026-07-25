"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";
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
      const res = await fetch(getApiUrl("/sessions"));
      const data = (await res.json()) as Session[];

      const withPreviews = await Promise.all(
        data.map(async (session) => {
          const msgRes = await fetch(
            getApiUrl(`/sessions/${session.id}/messages`),
          );
          const msgs = (await msgRes.json()) as { content?: string }[];
          const first = msgs[msgs.length - 1];

          return {
            ...session,
            firstMessage: first?.content?.slice(0, 48) || "New session",
          };
        }),
      );

      setSessions(withPreviews);
    }

    fetchSessions();
  }, [activeSessionId]);

  return (
    <aside className="flex h-full w-68 shrink-0 flex-col border-r border-gray-800 bg-gray-950">
      <div className="border-b border-gray-800 px-4 py-4">
        <h1 className="text-base font-semibold text-gray-100">PDF Chat</h1>
        <p className="mt-1 text-xs text-gray-500">Research workspace</p>
      </div>

      <div className="p-3">
        <button
          type="button"
          onClick={onNewChat}
          className="w-full rounded-md bg-teal-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-500"
        >
          New Chat
        </button>
      </div>

      <div className="flex-1 space-y-1 overflow-y-auto px-2 pb-3">
        {sessions.map((session) => {
          const isActive = activeSessionId === session.id;

          return (
            <button
              key={session.id}
              type="button"
              onClick={() => onSelectSession(session.id)}
              className={`w-full rounded-md px-3 py-2 text-left transition-colors ${
                isActive
                  ? "bg-gray-800 text-gray-100"
                  : "text-gray-400 hover:bg-gray-900 hover:text-gray-200"
              }`}
            >
              <p className="truncate text-sm">{session.firstMessage}</p>
              <p className="mt-1 text-xs text-gray-600">
                {new Date(session.created_at).toLocaleDateString()}
              </p>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
