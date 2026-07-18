import type { Finding } from "@/lib/types";
import { money } from "@/lib/types";

type Props = {
  findings: Finding[];
  selectedId?: string;
  onSelect: (id: string) => void;
};

export function FindingList({ findings, selectedId, onSelect }: Props) {
  return (
    <section className="min-w-0 border-r border-[var(--line)] bg-white">
      <div className="flex items-center justify-between border-b border-[var(--line)] px-5 py-4">
        <div>
          <p className="text-sm font-semibold">Investigation checklist</p>
          <p className="mt-1 text-xs text-[var(--muted)]">Results requiring auditor judgement</p>
        </div>
        <span className="rounded-md bg-[var(--danger-soft)] px-2 py-1 text-xs font-semibold text-[var(--danger)]">
          {findings.length} findings
        </span>
      </div>
      <div className="grid grid-cols-[1fr_110px_86px] border-b border-[var(--line)] bg-[var(--soft)] px-5 py-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        <span>Procedure</span><span>Result</span><span className="text-right">Amount</span>
      </div>
      <div>
        {findings.map((finding) => (
          <button
            key={finding.id}
            onClick={() => onSelect(finding.id)}
            className={`grid w-full grid-cols-[1fr_110px_86px] items-start gap-3 border-b border-[var(--line)] px-5 py-5 text-left transition ${selectedId === finding.id ? "bg-[#f7f6f2]" : "hover:bg-[var(--soft)]"}`}
          >
            <div>
              <p className="text-sm font-medium leading-5">{finding.title}</p>
              <p className="mt-2 font-mono text-[10px] text-[var(--muted)]">{finding.rule_id}</p>
            </div>
            <span className={`result-chip ${finding.severity === "high" ? "failed" : "review"}`}>
              {finding.severity === "high" ? "Failed" : "Review"}
            </span>
            <span className="text-right font-mono text-xs font-semibold">
              {money(finding.amount, finding.currency).replace(",00", "")}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

