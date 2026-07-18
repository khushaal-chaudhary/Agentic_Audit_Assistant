import type { Finding } from "@/lib/types";
import { money } from "@/lib/types";

type Props = { finding?: Finding };

function locator(finding: Finding, index: number) {
  const evidence = finding.evidence[index];
  if (evidence.sheet) return `${evidence.sheet} · ${evidence.cell_range ?? "cell"}`;
  if (evidence.row) return `row ${evidence.row}`;
  return evidence.passage ?? evidence.locator_type;
}

export function EvidencePanel({ finding }: Props) {
  if (!finding) {
    return (
      <section className="grid min-w-0 place-items-center bg-[#faf9f6] p-10 text-center">
        <div className="max-w-sm">
          <p className="text-lg font-semibold">Run the audit agent</p>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            Findings will open beside their exact source rows, cells, and passages.
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
        <div className="flex items-center gap-2">
          <span className="result-chip prepared">Prepared</span>
          <button className="rounded-md border border-[var(--line)] px-2 py-1 text-xs">Review⌄</button>
        </div>
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

          <div className="my-6 h-px bg-[var(--line)]" />
          <p className="text-[10px] font-semibold uppercase tracking-[0.13em] text-[var(--muted)]">Source evidence</p>
          <div className="mt-3 space-y-3">
            {finding.evidence.map((evidence, index) => (
              <div className="rounded-lg border border-[var(--line)] bg-[#fbfbf9] p-3" key={`${evidence.document}-${index}`}>
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-[11px] font-semibold">{evidence.document}</p>
                  <span className="source-chip">{locator(finding, index)}</span>
                </div>
                <p className="mt-2 border-l-2 border-[var(--mint-strong)] pl-3 text-xs leading-5 text-[var(--muted)]">
                  {evidence.excerpt}
                </p>
              </div>
            ))}
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

