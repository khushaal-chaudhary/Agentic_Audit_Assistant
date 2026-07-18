import type { IntegrationStatus } from "@/lib/types";

type Props = { integrations: IntegrationStatus | null };

const items = [
  ["⌂", "Overview"],
  ["□", "Dossier"],
  ["▤", "Documents"],
  ["!", "Findings"],
  ["⌘", "Data analysis"],
  ["✓", "Review"],
];

export function AppSidebar({ integrations }: Props) {
  return (
    <aside className="flex min-h-screen w-[250px] shrink-0 flex-col bg-[var(--green)] px-4 py-5 text-white">
      <div className="flex items-center gap-3 px-2">
        <div className="grid h-9 w-9 place-items-center rounded-full border border-white/30 text-sm font-semibold">A</div>
        <div>
          <p className="font-semibold">AuditGraph</p>
          <p className="text-[11px] text-white/55">Quality workspace</p>
        </div>
      </div>

      <button className="mt-7 flex items-center justify-between rounded-xl bg-white/10 px-3 py-3 text-left text-sm">
        <span>Muster Verpackungen</span><span className="text-white/50">⌄</span>
      </button>

      <nav className="mt-5 space-y-1">
        {items.map(([icon, label], index) => (
          <button
            key={label}
            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm ${index === 3 ? "bg-white text-[var(--green)]" : "text-white/70 hover:bg-white/10"}`}
          >
            <span className="w-5 text-center text-xs">{icon}</span>{label}
          </button>
        ))}
      </nav>

      <div className="mt-auto space-y-2 rounded-xl border border-white/10 bg-black/10 p-3 text-xs">
        <p className="font-medium">Connections</p>
        <div className="flex items-center justify-between text-white/65">
          <span>Cognee graph</span>
          <span className={integrations?.cognee.configured ? "text-[var(--mint)]" : ""}>
            {integrations?.cognee.configured ? "Connected" : "Local only"}
          </span>
        </div>
        <div className="flex items-center justify-between text-white/65">
          <span>OpenAI</span>
          <span className={integrations?.openai.configured ? "text-[var(--mint)]" : ""}>
            {integrations?.openai.configured ? "Connected" : "Local only"}
          </span>
        </div>
      </div>
    </aside>
  );
}

