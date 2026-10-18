"use client";

import { useEffect, useRef, useState } from "react";
import { Send, Trash2, HelpCircle, Loader2 } from "lucide-react";
import clsx from "clsx";
import { Card, Button } from "@/components/ui/primitives";
import { CitationChip } from "@/components/evidence/CitationChip";
import { EvidencePanel, EvidenceTarget } from "@/components/evidence/EvidencePanel";
import { api, ApiError } from "@/lib/api";
import type { ChatMessage, Citation } from "@/types";

const SUGGESTED_QUESTIONS = [
  "What are my main obligations?",
  "What is the termination notice period?",
  "What happens if I breach the agreement?",
  "Who owns the intellectual property?",
  "Are there any potential risks?",
  "What happens after the contract expires?",
];

export function ChatPanel({ documentId }: { documentId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidenceTarget, setEvidenceTarget] = useState<EvidenceTarget | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  function openEvidence(citation: Citation) {
    setEvidenceTarget({
      documentId: citation.document_id || documentId,
      pageNumber: citation.page_number,
      quote: citation.quote || citation.snippet,
      chunkId: citation.chunk_id,
      label: "Cited passage",
    });
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send(message: string) {
    if (!message.trim() || loading) return;
    setError(null);
    setInput("");

    const userMsg: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: message,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const res = await api.sendChatMessage(documentId, message, conversationId);
      setConversationId(res.conversation_id);
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}-a`,
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          confidence: res.confidence,
        },
      ]);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setMessages([]);
    setConversationId(undefined);
    setError(null);
  }

  return (
    <Card className="flex flex-col h-[640px]">
      <div className="flex items-center justify-between px-6 py-4 border-b border-line">
        <div>
          <h3 className="font-serif text-lg font-semibold">Ask LexClarity</h3>
          <p className="text-xs text-ink-faint">Ask questions about your document.</p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="flex items-center gap-1.5 text-xs text-ink-faint hover:text-risk-high transition-colors"
          >
            <Trash2 size={13} /> Clear chat
          </button>
        )}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center px-4">
            <HelpCircle size={26} className="text-ink-faint mb-3" strokeWidth={1.5} />
            <p className="text-sm text-ink-faint mb-5 max-w-xs">
              Ask anything about this document. Answers are grounded in its text, with
              citations to the page and section they come from.
            </p>
            <div className="flex flex-wrap gap-2 justify-center max-w-sm">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="text-xs rounded-full border border-line bg-white px-3 py-1.5 text-ink-soft hover:border-navy hover:text-navy transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <ChatBubble key={m.id} message={m} onOpenEvidence={openEvidence} />
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-ink-faint text-sm">
            <Loader2 size={14} className="animate-spin" />
            <span>LexClarity is reading the document…</span>
          </div>
        )}

        {error && (
          <p className="text-sm text-risk-high bg-risk-highBg rounded-md px-3 py-2">{error}</p>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="border-t border-line p-4 flex items-center gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about this document…"
          className="flex-1 rounded-md border border-line bg-white px-3.5 py-2.5 text-sm outline-none focus:border-navy"
        />
        <Button type="submit" size="sm" disabled={loading || !input.trim()}>
          <Send size={14} />
        </Button>
      </form>

      <EvidencePanel
        target={evidenceTarget}
        onClose={() => setEvidenceTarget(null)}
      />
    </Card>
  );
}

function ChatBubble({
  message,
  onOpenEvidence,
}: {
  message: ChatMessage;
  onOpenEvidence: (c: Citation) => void;
}) {
  const isUser = message.role === "user";
  return (
    <div className={clsx("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={clsx("max-w-[85%]", isUser ? "items-end" : "items-start")}>
        <div
          className={clsx(
            "rounded-lg px-4 py-3 text-sm leading-relaxed",
            isUser ? "bg-navy text-white" : "bg-paper border border-line text-ink-soft"
          )}
        >
          {message.content}
        </div>
        {message.confidence === "low_confidence" && (
          <p className="mt-1.5 text-xs text-brass italic">
            Low confidence — one or more claims could not be fully verified
            against the document.
          </p>
        )}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2 space-y-1.5">
            {message.citations.map((c, i) => (
              <CitationChip key={i} citation={c} onOpen={onOpenEvidence} />
            ))}
          </div>
        )}
        {!isUser && message.confidence === "not_found" && (
          <p className="mt-1.5 text-xs text-ink-faint italic">
            Not found in the uploaded document.
          </p>
        )}
      </div>
    </div>
  );
}
