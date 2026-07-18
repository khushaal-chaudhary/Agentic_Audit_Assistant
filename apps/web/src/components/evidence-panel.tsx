import type { Finding } from "@/lib/types";
import { evidenceLocator, evidenceUrl, money } from "@/lib/types";

type Props = { finding?: Finding; apiUrl: string; jobId?: string };

export function EvidencePanel({ finding, apiUrl, jobId }: Props) {
  if (!finding) {
    return (
      <section className="grid min-w-0 place-items-center bg-[#faf9f6] p-10 text-center">
        <div className="max-w-sm">
          <p className="text-lg font-semibold">Run the audit agent</p>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            Findings will open beside their exact source rows, cells, pages, and passages.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="min-w-0 bg-[#faf9f6]">
      <div className="flex items-center justify-between border-b border-[var(--line)] bg-white px-5 py-3">
        <div>
          <p className="text-xs font-semibold">{finding.evidence[0]?.document}</p>
          <p className="mt-1 text-[10px] text-[var(--muted)]">{finding.evidence.length} linked source locations</p>
        </div>
        <span className="result-chip prepared">Evidence bound</span>
      </div>

      <div className="h-[calc(100vh-214px)] overflow-y-auto p-5">
        <article className="mx-auto max-w-2xl rounded-sm border border-[var(--line)] bg-white px-8 py-7 shadow-sm">
          <div className="flex items-start justify-between gap-5">
            <div>
              <span className={`result-chip ${finding.severity === "high" ? "failed" : "review"}`}>
                {finding.category}
              </span>
              <h2 className="mt-4 text-xl font-semibold leading-7">{finding.title}</h2>
            </div>
            {finding.amount && (
              <div className="shrink-0 text-right">
                <p className="text-[10px] uppercase tracking-[0.12em] text-[var(--muted)]">Exposure</p>
                <p className="mt-1 font-mono text-lg font-semibold">{money(finding.amount, finding.currency)}</p>
              </div>
            )}
          </div>
          <p className="mt-4 text-sm leading-6 text-[var(--muted)]">{finding.summary}</p>

          {finding.amount && finding.calculation && (
            <section
              aria-label="Exact calculation trace"
              className="mt-6 overflow-hidden rounded-xl border border-[var(--line)]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 bg-[var(--mint)] px-4 py-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--green)]">
                    Exact calculation trace
                  </p>
                  <p className="mt-1 text-xs text-[var(--green)]">
                    {finding.calculation.operation.toUpperCase()} · {finding.calculation.terms.length} source value(s)
                  </p>
                </div>
                <span className="result-chip passed">Recomputed</span>
              </div>
              <div className="divide-y divide-[var(--line)] bg-white">
                {finding.calculation.terms.map((term, index) => {
                  const content = (
                    <>
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-semibold">{term.label}</span>
                        <span className="mt-1 block truncate text-[10px] text-[var(--muted)]">
                          {term.evidence.document} · {evidenceLocator(term.evidence)}
                        </span>
                      </span>
                      <span className="shrink-0 font-mono text-xs font-semibold">
                        {money(term.value, finding.calculation?.currency)}
                      </span>
                    </>
                  );
                  const className =
                    "flex items-center justify-between gap-4 px-4 py-3 hover:bg-[var(--soft)]";
                  const key = [
                    term.evidence.document,
                    term.evidence.row ?? index,
                    term.label,
                  ].join("-");
                  return jobId ? (
                    <a
                      className={className}
                      href={evidenceUrl(apiUrl, jobId, term.evidence)}
                      key={key}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {content}
                    </a>
                  ) : (
                    <div className={className} key={key}>
                      {content}
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center justify-between border-t border-[var(--line)] bg-[#fbfbf9] px-4 py-3">
                <span className="text-xs font-semibold">Recomputed total</span>
                <span className="font-mono text-sm font-semibold">
                  {money(finding.amount, finding.calculation.currency)}
                </span>
              </div>
            </section>
          )}

          <div className="my-6 h-px bg-[var(--line)]" />
          <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--muted)]">Source evidence</p>
          <div className="mt-3 space-y-3">
            {finding.evidence.map((evidence, index) => {
              const body = (
                <>
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate text-[11px] font-semibold">{evidence.document}</p>
                    <span className="source-chip">{evidenceLocator(evidence)}</span>
                  </div>
                  <p className="mt-2 border-l-2 border-[var(--mint-strong)] pl-3 text-xs leading-5 text-[var(--muted)]">
                    {evidence.excerpt}
                  </p>
                </>
              );
              return jobId ? (
                <a
                  className="block rounded-lg border border-[var(--line)] bg-[#fbfbf9] p-3 hover:border-[var(--mint-strong)]"
                  href={evidenceUrl(apiUrl, jobId, evidence)}
                  key={`${evidence.document}-${index}`}
                  rel="noreferrer"
                  target="_blank"
                >
                  {body}
                </a>
              ) : (
                <div className="rounded-lg border border-[var(--line)] bg-[#fbfbf9] p-3" key={`${evidence.document}-${index}`}>
                  {body}
                </div>
              );
            })}
          </div>

          <div className="mt-6 rounded-lg bg-[var(--mint)] p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--green)]">Recommended audit step</p>
            <p className="mt-2 text-sm leading-5 text-[var(--green)]">{finding.next_step}</p>
          </div>
        </article>
      </div>
    </section>
  );
}
