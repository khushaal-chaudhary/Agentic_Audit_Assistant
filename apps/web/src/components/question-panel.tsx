"use client";

import { FormEvent, useState } from "react";

import {
  evidenceLocator,
  evidenceUrl,
  type GroundedAnswer,
} from "@/lib/types";

type Props = {
  apiUrl: string;
  jobId?: string;
};

export function QuestionPanel({ apiUrl, jobId }: Props) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<GroundedAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!jobId || question.trim().length < 2) return;
    setLoading(true);
    setError(undefined);
    try {
      const response = await fetch(`${apiUrl}/api/dossiers/${jobId}/questions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim() }),
      });
      if (!response.ok) {
        const payload = (await response.json()) as { detail?: string };
        throw new Error(payload.detail ?? `Request failed with status ${response.status}`);
      }
      setAnswer((await response.json()) as GroundedAnswer);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The question could not be answered.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-2xl border border-[var(--line)] bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">Ask the audit file</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Answers are limited to validated findings and carry source-level citations.
          </p>
        </div>
        {answer && (
          <span className="result-chip passed">
            {answer.provider === "openai" ? "OpenAI · grounded" : "Deterministic fallback"}
          </span>
        )}
      </div>
      <form className="mt-3 flex gap-2" onSubmit={ask}>
        <input
          className="min-w-0 flex-1 rounded-lg border border-[var(--line-strong)] px-3 py-2 text-sm outline-none focus:border-[var(--accent)]"
          disabled={!jobId || loading}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={jobId ? "Which findings indicate a control override?" : "Run a dossier before asking a question"}
          value={question}
        />
        <button
          className="rounded-lg bg-[var(--green)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
          disabled={!jobId || loading || question.trim().length < 2}
        >
          {loading ? "Checking…" : "Ask ↑"}
        </button>
      </form>
      {error && <p className="mt-3 text-xs text-[var(--danger)]">{error}</p>}
      {answer && (
        <div className="mt-4 space-y-3">
          {answer.claims.map((claim, claimIndex) => (
            <article className="rounded-xl border border-[var(--line)] bg-[var(--soft)] p-4" key={claimIndex}>
              <p className="text-sm leading-6">{claim.statement}</p>
              <details className="mt-3">
                <summary className="cursor-pointer text-xs font-semibold text-[var(--accent)]">
                  {claim.evidence.length} exact source location(s)
                </summary>
                <div className="mt-2 grid gap-2 md:grid-cols-2">
                  {claim.evidence.map((evidence, evidenceIndex) => (
                    <a
                      className="rounded-lg border border-[var(--line)] bg-white p-3 text-xs hover:border-[var(--mint-strong)]"
                      href={evidenceUrl(apiUrl, jobId!, evidence)}
                      key={`${evidence.sha256}-${evidenceIndex}`}
                      rel="noreferrer"
                      target="_blank"
                    >
                      <span className="font-semibold">{evidence.document}</span>
                      <span className="ml-2 text-[var(--muted)]">{evidenceLocator(evidence)}</span>
                      <span className="mt-2 block leading-5 text-[var(--muted)]">{evidence.excerpt}</span>
                    </a>
                  ))}
                </div>
              </details>
            </article>
          ))}
          <p className="text-xs text-[var(--muted)]">{answer.note}</p>
        </div>
      )}
    </section>
  );
}
