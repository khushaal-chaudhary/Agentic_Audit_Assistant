# Architecture

## Invariants

1. The evidence ledger is authoritative for facts, calculations, and findings.
2. Cognee is a semantic/graph projection, not the authority for arithmetic or citations.
3. Deterministic rules evaluate amounts, dates, identities, and matches before model reasoning.
4. Every monetary value is a `Decimal` derived from a source value or a disclosed calculation.
5. Missing support is represented as `not_testable`; it is not evidence of fraud by itself.

## Demo topology

- Next.js UI runs locally on port 3000.
- FastAPI and document processing run locally on port 8000.
- Uploaded dossiers, job status, and evidence reports live under ignored `data/runtime`.
- The backend makes outbound calls to Cognee Cloud and OpenAI only when keys are configured.
- The sample deterministic checks run with no cloud credentials.

For a hosted UI talking to the laptop, expose only the API through a temporary free HTTPS tunnel and
set `NEXT_PUBLIC_API_URL` before building the web app. Running both services locally is the default.

## Optional production topology

- Web UI: Vercel.
- Database/auth/private storage: Supabase Free.
- Python API and dossier jobs: Google Cloud Run with minimum instances zero.
- Semantic graph: Cognee Cloud credits.
- Extraction/reasoning: OpenAI API credits.

The repository includes a Cloud Run-ready container, but deployment is intentionally deferred until
an eligible billing account is available.

## Cost controls

- Hash and cache document extraction results.
- Run deterministic rules before any model call.
- Send only validated finding context to OpenAI.
- Cognee receives the typed evidence-graph projection and validated report excerpts by default;
  raw ledgers remain local. Cognee is never authoritative for arithmetic or citations.
- Use `gpt-5-nano` for classification and `gpt-5.4-mini` only for ambiguous reasoning.
