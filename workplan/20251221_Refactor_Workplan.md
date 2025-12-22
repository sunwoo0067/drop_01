# Refactor Workplan (dev2)

## Goals
- Support bulk catalog ingestion: sourcing -> normalization -> listing -> order sync without gaps.
- Detect/rollback for policy, stock, price changes.
- Source of truth is local PostgreSQL; external exposure/automation via Supabase.
- Every stage records state with retry/rollback.

## Principles
- Keep legacy code intact; reuse when safe, rewrite when it improves clarity/robustness.
- Refactor incrementally by feature slice.
- New local PostgreSQL DB (no Docker).
- Track all work under dev2 branch.

## Open Decisions
- Repo strategy: stay in current repo (preferred) vs new repo (only if full rewrite/clean history).
- Supabase scope: which flows are hosted (Edge Functions, Storage, DB sync)?
- Minimal first slice: which single workflow to refactor first?

## Phased Plan
1) Inventory + Scope
   - List current workflows, scripts, and integrations.
   - Define what to keep, drop, or rework.
   - Pick the first feature slice to refactor.

2) Local DB v2
   - Create new local Postgres database.
   - Define connection config and env vars.
   - Decide migration strategy (fresh schema vs migration from current).

3) State Model
   - Define pipeline states (sourcing/normalize/list/order) and retry/rollback rules.
   - Map state transitions and failure handling.

4) Feature Slice 1
   - Refactor first workflow end-to-end.
   - Add targeted tests/scripts for the slice.

5) Supabase Integration Plan
   - Define Edge Functions needed (public/webhook/auth).
   - Storage usage for assets.
   - Sync or replication strategy with local Postgres.

6) Observability
   - Standardized logging and failure snapshots.
   - Metrics/alerts for policy/stock/price changes.

## TODO (Immediate)
- Confirm repo direction (current repo + dev2 vs new repo).
- Choose the first feature slice to refactor.
- Define the new local DB name and credentials.
- Identify minimal state machine for pipeline v2.
- List integrations to keep (Coupang, OwnerClan, Gemini, etc.).
