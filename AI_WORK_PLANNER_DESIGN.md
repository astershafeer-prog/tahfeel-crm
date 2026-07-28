# AI Work Planner — Technical Design Document

Status: **DRAFT — awaiting approval. No code has been written.**
Scope: design only, per explicit instruction to study the codebase and propose before implementing.

---

## 0. Honest assessment before the design

The product brief asks for 17 deliverables: daily/weekly/monthly planners, a revenue engine, a compliance engine, an industry-specific requirement engine, a government-regulation-tracking engine, a relationship engine, a lead engine, and an LLM narrative layer on top. Read literally, that's a small product, not a feature.

What I found in the codebase changes the calculus a lot in your favor for **most** of it, but not all of it:

- **Cheap, mostly reuse (Phase 1):** renewal urgency, compliance scoring, revenue-at-risk, dormancy/relationship gaps, lead follow-up — all of this data and most of the math already exists in `app.py` (`_renewal_budget_range`, the `dl(d)` days-to-expiry pattern used in 6 places, `Lead.due_date`/`status`, `CustomerCall`, the `/analytics` dormancy scan). Building a page that aggregates and ranks these into "here's your day" is genuinely a data-aggregation + UI job, not an AI-research job. No LLM is required to get 80% of the stated value ("who to call, why, how much").
- **New capability, real cost (Phase 3):** two of the requested engines — **industry-specific compliance requirements** (DHA/SIRA/DTCM/RERA/Municipality mapped to business activity) and **Government Intelligence** (tracking regulation changes and who's affected) — have **zero existing groundwork**. There's no field anywhere that says "a Restaurant needs a Dubai Municipality food license." Building this properly means a new admin-maintained reference table, and someone (you, or ops) has to keep it accurate as UAE rules change. This is not a "flip a switch" feature — it's a content-maintenance commitment. I'd rather say that now than build a shiny page that quietly goes stale in 6 months.
- **Optional and separable: the LLM narrative layer.** The "Good morning Aslam..." prose and "what should I say" call scripts genuinely benefit from an LLM. But the underlying facts (dates, AED amounts, names) must **never** come from the LLM — they must be computed deterministically and injected into the prompt, with the LLM only doing phrasing. This protects you from a hallucinated expiry date or revenue figure reaching a salesperson. I've designed it that way below.

**My recommendation:** build Phase 1 (deterministic planner, no LLM, no new dependencies) first, ship it, see if reps actually use it daily. Then decide whether the LLM narrative layer and the industry/government engines are worth the ongoing cost. Below is the full design for all phases so you can see the whole shape, but Phase 1 is what I'd actually start building.

---

## 1. Product Vision

Replace the sales rep's mental triage ("who do I call today?") with a single ranked list, generated from data already in the CRM, that answers: **who, why, what's the opportunity, what do I click**. It is not a new dashboard — it's the front door. It sits at `/planner` (new route), reachable from `nav()`, and can eventually replace `/desk` as the default landing page after login.

Every recommendation is a **row that maps to a real CRM record** (a Customer, a Lead, a Document) with a **reason** (data-derived, not vague), an **estimated value** where applicable, and **one-click actions** that hit routes that already exist (`tel:`, WhatsApp send modal, `/jobs/add`, `/customers/<id>/calls/add`, `/customers/<id>`).

## 2. User Journey

1. Rep logs in → lands on `/planner` (or clicks a new "Work Planner" nav item next to "My Desk").
2. Sees a ranked "Today" list (max ~10 items, not a wall of data) grouped by category with a color-coded urgency badge (reusing the existing red/amber/green convention from `renewal_pipeline_board.html`).
3. Each card: customer/lead name, one-line reason, estimated AED opportunity (if any), and action buttons that reuse existing UI components (`_wa_send_modal.html`, `tel:` links, links into `/customers/<id>`, `/jobs/add?customer_id=`).
4. Rep clicks an action → does the real thing in the existing CRM screen (call log, WhatsApp, job creation). No new "do the task here" UI is built — the planner **routes to** existing workflows, it doesn't duplicate them.
5. Rep can mark a suggestion "Done" or "Not now" (snooze/dismiss) → this writes to a new `WorkPlanItem` table so the same suggestion doesn't reappear every day and so a manager can later see what was surfaced and what happened to it.
6. Monday morning: same page shows a "This Week" tab. First of the month: a "This Month" tab.

## 3. AI Decision Logic

"AI" here means a **deterministic, explainable scoring engine**, not a black box. Every recommendation must be traceable to a rule and a data point — critical for a compliance/finance-adjacent tool where a wrong or hallucinated figure has real cost. The engine runs as a scheduled job (see §16), not on every page load, so it can be reviewed/audited before reps see it.

Decision categories (mirrors the brief, mapped to real data):

| Category | Source data | Existing helper to reuse |
|---|---|---|
| Renewal opportunity | `Document.expiry_date`, `doc_type` | `dl(d)` days-left pattern (6 call sites today → should be centralized into one function during implementation) |
| Compliance risk | `Document` expired/expiring counts, `ComplianceSnapshot` | `_compute_client_snapshot_metrics`, `compliance_report()` scoring |
| Relationship/dormancy | `CustomerCall.called_at`, `Job` last-touch | `/analytics` dormancy scan (8630-8645), extended to also check `CustomerCall` (analytics today only checks last Job touch, which under-counts relationship calls with no job) |
| Sales/cross-sell | `Customer.jurisdiction`/`business_activity` + absence of certain `Job.job_type` history | New logic (see §9) |
| Lead follow-up | `Lead.status`, `Lead.due_date`, `Lead.genuine` | existing `/dashboard` overdue-lead logic (2034-2037) |
| Government/industry | New reference data | None exists — Phase 3 |

## 4. Recommendation Engine

For each active rep, for each of their assigned Customers/Leads (via `Customer.assigned_to`, `Lead.assigned_to` — already how ownership works, no change needed), run the rule set below and emit zero or more `WorkPlanItem` candidates. Rules are simple, independently testable functions — not a monolith:

```
renewal_rule(customer)      -> items where a Document expires within 30/14/7 days
compliance_rule(customer)   -> items where compliance score dropped or docs expired
dormancy_rule(customer)     -> items where days-since-last-touch crosses 30/60/90/180
lead_followup_rule(lead)    -> items where Lead.due_date is today/overdue, or status stuck
cross_sell_rule(customer)   -> items where a service gap is detected (Phase 2, needs definition — see §9)
```

Each rule returns `{category, reason_text, estimated_value_min, estimated_value_max, urgency_days, entity_type, entity_id}`. Reason text is a template, not free text: e.g. `"Trade License expires in {n} days"`, `"No contact in {n} days"` — deterministic, no LLM involved at this stage.

## 5. Prioritisation Algorithm

A single weighted score ranks all candidate items across categories so "Today's Priority" isn't just "all renewals then all leads" but a genuine mixed ranking:

```
score = w_urgency   * urgency_score(days_to_deadline)      # closer = higher, capped at 0 for >90d
      + w_revenue    * revenue_score(estimated_value_max)   # log-scaled, so 8k and 80k aren't 10x apart in weight
      + w_compliance * compliance_risk_score(status)        # expired > expiring > gap
      + w_dormancy   * dormancy_score(days_since_contact)   # 180d > 90d > 60d > 30d
      + w_lead       * lead_score(overdue_days, lead_value_tier)
```

Weights (`w_urgency`, `w_revenue`, etc.) are stored in the existing `AppSetting` key-value table — **no new config system needed**, this table already exists and is already used for toggles like `automation_on('auto_expiry_wa')`. This lets you retune "what the AI cares about" without a deploy.

Cap the daily list at ~10 items per rep (configurable) so it stays a triage tool, not another report. Anything beyond the cap still exists in the underlying data and shows up on the Week/Month view.

## 6. Dashboard Layout

Reuses the existing design system exactly (`static/css/tahfeel.css`, `macros.html` `topbar()`/`nav()`, `.card`/`.card-stat`/`.due-pill` classes, the red/amber/green urgency palette from `renewal_pipeline_board.html`) — no new framework, no new visual language.

```
[topbar()]  [nav('planner')]

"Good morning, {FirstName}"   <- reuse welcome() macro pattern from dashboard_admin.html
Today's Priorities (N)   |   Potential Revenue Today: AED {sum}

┌─────────────────────────────────────────────┐
│ [urgency-color left border]                  │
│ ABC Restaurant  · Trade License · 14 days     │
│ Call today · Est. AED 8,000                   │
│ [📞 Call] [💬 WhatsApp] [📝 Task] [👤 Profile] │
└─────────────────────────────────────────────┘
... (up to ~10 cards, sorted by score desc)

Tabs: [Today] [This Week] [This Month]
Below the fold: "3 quotations awaiting follow-up" / "2 leads overdue" — small link-out rows,
reusing the needs_attention_banner() pill pattern already in macros.html.
```

Action buttons map directly to existing routes — no new backend needed for the actions themselves:
- Call → `tel:{phone}`
- WhatsApp → include `_wa_send_modal.html`, same as `customer_detail.html`
- Create Task → `/jobs/add?customer_id={id}`
- Open Profile → `/customers/{id}`
- Compliance Report → `/customers/{id}/health`

## 7. Weekly Planning Engine

Every Monday (cron), aggregate the same rule outputs over a 7-day window per rep, plus:
- Revenue forecast: sum of `estimated_value` across the week's items (min/max range, using existing `DocRenewalCost` ranges — don't present a false-precision single number).
- A simple suggested schedule: bucket items into weekdays by urgency (most urgent → Monday/Tuesday), not a calendar-integration feature — just an ordered list with a suggested day label. Full calendar sync is out of scope for v1 (no calendar integration exists in the codebase today).

## 8. Monthly Planning Engine

First of the month (cron): same aggregation over 30/60/90-day windows, plus a renewal pipeline summary reusing `renewal_pipeline_board()`'s bucket logic (Expired/≤30/31-60/61-90/90+) scoped to the rep's own customers, and a target-vs-forecast comparison using the existing `MonthlyTarget` model (already has `amount_target`, `lead_target`, `conversion_target` per user/month — reuse directly, don't duplicate).

## 9. Revenue Opportunity Engine

- **Renewals:** reuse `_renewal_budget_range(doc_types, jurisdiction)` (line ~6494) directly — it already sums `DocRenewalCost.renewal_cost_min_aed/max_aed` for a customer's expiring doc types, jurisdiction-aware. This is the single most reusable piece of logic in the whole codebase for this feature.
- **Cross-sell (additional visas, corporate tax, VAT, PRO, trademark, etc.):** genuinely new logic, because there's no "customer needs X but doesn't have it" flag anywhere. Honest scoping: a reliable cross-sell signal needs a rule like *"customer has `corp_tax_status='Not filed'` and `corp_tax_due_date` approaching"* (data exists — `Customer.corp_tax_status`, `vat_status` are real fields, this part is cheap) versus *"this customer might want a trademark"* which has **no data signal in the CRM at all** — that would be a guess dressed up as AI. Recommendation: implement the cross-sell rules that map to real fields (VAT, corp tax, additional visa via employee headcount trends) and explicitly skip services with no underlying signal (trademark, branch registration) until there's real usage data to key off, rather than inventing a heuristic that looks smart but isn't grounded.

## 10. Compliance Recommendation Engine

- **Expired/expiring (Phase 1, reuse):** exactly what `compliance_report()` and `renewal_pipeline_board()` already compute — expired/expiring `Document` rows, scored via the existing 0-100 formula. No new logic.
- **Missing approvals by industry (Phase 3, new):** requires a new admin-maintained table `IndustryComplianceRequirement` (business activity → required doc type → authority), because `Customer.business_activity` is currently a free-text string with no link to what documents that activity legally requires. Flag: this table needs a real owner to keep it accurate (UAE authority rules change) — it is not "set once and forget."

## 11. Government Update Engine

No existing groundwork at all. Proposed as a new lightweight **admin-authored** feature, not an automated regulation-scraper (scraping/monitoring UAE government sources reliably is its own project and a maintenance burden I would not recommend taking on inside this CRM): an admin manually posts a `RegulatoryUpdate` (title, description, effective date, affected business activities/jurisdiction). The engine then matches it against `Customer.business_activity`/`jurisdiction`/`emirate` and surfaces it as a planner item for the owning rep ("share this update with 6 affected customers"). This turns a manual "someone read the news" step into a targeted distribution tool — realistic scope, not a promise of automatic regulation detection.

## 12. Relationship Management Engine

Dormancy buckets (30/60/90/180 days) computed from **the more recent of** `CustomerCall.called_at` and last `Job` activity (JobUpdate timestamp) — the existing `/analytics` dormancy scan only checks Job activity, which would wrongly flag a customer as dormant if a rep called them but no job exists yet. This is a small, worthwhile correction to make while building this anyway. Suggested action for dormant customers: a plain relationship call, no sales pitch required — matches the brief's intent and avoids constant "buy more" pressure that could hurt account relationships.

## 13. Lead Prioritisation Engine

Entirely reuses existing fields — no new schema:
- Overdue: `Lead.due_date < now` and `status not in ('Converted','Lost')` (same filter `/dashboard` already uses).
- Stuck/no-activity: `status='Qualified'` or `'Proposal'` with no `LeadUpdate` in N days (join `LeadUpdate` by `lead_id`, max `created_at`).
- Lost-worth-reopening: `status='Lost'` with a `lost_reason` that isn't "not interested"/"went to competitor permanently" (needs a light categorization pass on `lost_reason` values already in the DB — a one-time data check before deciding what's "reopenable").
- New/ungenuine-unset: `genuine IS NULL` — these are leads nobody has qualified yet, a real gap the CRM already tracks but doesn't surface proactively.

## 14. Database Fields / Tables Required

**New table: `WorkPlanItem`** (the backbone — persists what the engine recommended, so it's auditable and doesn't repeat itself):
```
id, run_date (Date), user_id (FK user.id), category (renewal/compliance/dormancy/lead/cross_sell/government),
entity_type (customer/lead/document), entity_id, reason_text, estimated_value_min, estimated_value_max,
urgency_days, score (Float), status (pending/done/dismissed/snoozed), dismissed_reason,
created_at, actioned_at
```
Unique constraint on `(user_id, entity_type, entity_id, category, run_date)` to prevent duplicate generation on re-run — same dedupe pattern already used by `AutoMessageLog.dedupe_key`.

**Phase 3 only — `IndustryComplianceRequirement`:**
```
id, business_activity_keyword, authority_name, required_doc_type, jurisdiction, mandatory (bool), notes, updated_at
```

**Phase 3 only — `RegulatoryUpdate`:**
```
id, title, description, effective_date, source_authority, affected_business_activities (text, comma-list or join table),
affected_jurisdiction, created_by (FK user.id), created_at, published (bool)
```

**No changes needed to:** `Customer`, `Lead`, `Job`, `Document`, `Owner` — all source data already exists. Explicitly **not** adding a stored `health_score` or `last_contacted_at` column to `Customer` — these are derived values that go stale; compute at plan-generation time the same way `ComplianceSnapshot` already treats score as a point-in-time snapshot, not a live field.

## 15. AI Prompts Required (Phase 2 only — narrative layer)

Used **only** to phrase already-computed facts, never to invent them. The deterministic engine (§3-§5) produces a structured JSON payload per rep per day; the LLM call receives that JSON and is instructed not to add any fact not present in it.

**Daily narrative prompt (system):**
```
You are a sales manager writing a 3-sentence morning briefing for {rep_name}.
You will receive a JSON list of prioritized work items. Summarize warmly and briefly.
Do not invent names, dates, or amounts not present in the JSON. Do not add advice beyond
what the data supports. If the JSON is empty, say so plainly — do not fabricate items.
```
User content: the day's `WorkPlanItem` list serialized as JSON.

**Call talking-points prompt (per item, on-demand — not pre-generated for all items to control cost):**
```
Given this customer/lead record and reason for contact: {reason_text}, {entity summary},
write 2-3 short talking points a salesperson could use on a call. Ground every claim in
the provided data. Do not mention prices/dates not given. Keep it under 60 words.
```

**Weekly/monthly summary prompt:** same pattern, larger JSON payload, longer output cap.

Provider choice, cost controls, and whether to build this at all is an open decision — see §17/questions below.

## 16. Automation Workflows

Extend the existing cron-endpoint pattern (`/cron/expiry-wa`, `/cron/birthday-wishes` — all `?key=CRON_KEY`-protected, hit by an external scheduler, deduped via a log table) rather than introducing a new scheduling mechanism:

- `/cron/generate-daily-plan` — runs early each morning, computes `WorkPlanItem` rows for every active rep, respects a new `automation_on('auto_daily_planner')` toggle (same helper already used for `auto_expiry_wa`).
- `/cron/generate-weekly-plan` — Mondays.
- `/cron/generate-monthly-plan` — 1st of month.
- LLM narrative generation (if built) is a **separate, optional** step after `WorkPlanItem` rows exist — batched once per rep per day, not called per page view, to keep cost bounded and predictable.
- No automatic WhatsApp sending is proposed from the planner itself — every action stays human-click-initiated, consistent with how the rest of the CRM treats outbound messaging and consistent with protecting WhatsApp number quality (this matters more than automation convenience).

## 17. Future Roadmap

- Manager view: aggregate `WorkPlanItem` across a team to answer "is my team working the plan?"
- Outcome tracking: correlate `WorkPlanItem` actions taken → actual `Job.revenue` closed, to eventually validate/retune the scoring weights with real data instead of guessed weights.
- Calendar integration for the weekly scheduler (not scoped now — no calendar system exists today).
- Automated government-source monitoring (explicitly deferred in §11 — real scraping reliability risk, not worth building until the manual version proves valuable).

---

## Open decisions (need your call before Phase 2/3, not Phase 1)

1. **LLM provider** for the narrative layer — Anthropic Claude vs. none-for-now (Phase 1 ships with zero LLM calls and zero added cost/dependency).
2. **Phase 1 scope confirmation** — build the deterministic planner (renewal + compliance + dormancy + lead prioritization, no cross-sell, no government/industry engine) as the actual first build?
3. **Cross-sell scope** — implement only the VAT/corp-tax/visa-headcount rules that have real data signal, explicitly skip trademark/branch-registration-style suggestions that have no underlying data (per §9)?
