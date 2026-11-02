# D10 — Pre-build design security review: identity gate and event model

**Date:** 2026-11-02 · **Reviewer:** security-reviewer agent · **Stage:** S2 → S4 precondition (spec decision D10)
**Scope (from `main` @ 498667e):** `docs/plans/IMPLEMENTATION_PLAN.md` §0 rules, §2 (M1), §2.1 identity-gate policy, §3 (M2), M4-T3; `docs/specs/INSMARTFIX_V1_SPEC.md` §3 FR-1, FR-5, FR-6, FR-7, §4.2–4.4, §5, NFR-6; `docs/design/INSMARTFIX_PRODUCT_DESIGN.md` §6.5, §13 ("R10").
**Method:** threat model per principal (contractor own / contractor other / contractor in another tenant / owner-FM same tenant / owner-FM other tenant / anonymous) × the 7 gated actions × the WO relationship, plus a walk of every §5 route, the event and completion write paths, and the web BFF.

---

## Verdict: **APPROVED WITH REQUIRED CHANGES**

The architecture is sound: one policy function, server-derived identity, `/me/*` aliases, an append-only event table, contractor serializer that omits `ranked_candidates`, argon2id with a constant-time miss path. Nothing found requires re-opening the design.

The review does find **7 high, 9 medium and 7 low** issues. The plan as written would let an owner act as a contractor, would rely on the dispatch layer (outside the gate, and outside the lock) to stop a past candidate taking someone else's live offer, scopes idempotency keys globally, leaves the CORRECTION chain unconstrained, and makes the append-only guarantee depend on which DB role the app happens to connect with.

All required fixes are **plan-level** and have been written into the affected tasks in `IMPLEMENTATION_PLAN.md` (§2.1 policy replaced, new §2.2, task rows, §9.2). Conditions:

1. **M1-T5 may merge** only once it implements the revised §2.1 policy and ships T-AUTH-14, T-AUTH-15 and T-AUTH-16. The security-reviewer gate on M1-T5 checks these.
2. Each other task listed in §2.2 of the plan must ship its listed D10 tests. The security-reviewer gate on that task's PR blocks until they pass.
3. Two **SPEC DELTAs** (below) are additive contract changes. They go to the product-manager for a G1 delta review and **do not block** M1-T5. Until they are approved, the interim behavior given for each applies.

Sign-off on code is per-PR (SEC-gated tasks) and again in M6-T7.

---

## Findings

Severity is the impact if the design is built as currently written. "Location" is a doc section or plan task.

### High

#### H-1 · Owner/FM "override" lets an owner accept, decline, transition, upload and complete as a contractor
- **Location:** Plan §2.1 row "Owner/FM, same tenant → allow"; spec §5 role column; FR-1.4; design §13.
- **Exploit:** an owner (or a compromised owner account) calls `POST /contractor/{marco}/accept/{wo}`, then `/workorders/{wo}/complete` with an arbitrary `failure_code`. The gate allows every action for owner/FM, so the WO is bound to Marco without his consent and a calibration label is written under his name. This poisons calibration and the audit trail, and it is invisible to Marco until he opens the job. The §5 contract already limits accept/decline to "contractor (own)" and transition/photos/complete to "bound contractor". The plan's table contradicts it.
- **Fix:** owner/FM override is **read-only** in v1: `schedule` and `get_wo` are allowed tenant-wide, and every mutating contractor action → **403**. A principal with no `contractor_id` calling any `/me/{schedule,accept,decline}` route → **403**. If the product later wants dispatcher-acting-on-behalf, that is a new feature with explicit `on_behalf_of` attribution and a spec delta. This aligns the plan with §5. It is not a spec change (see clarification C-3).

#### H-2 · Past-candidate accept/decline is authorized by the dispatch layer, outside the gate and outside the lock
- **Location:** Plan §2.1 row "past candidate → allow through the gate → dispatch returns 409"; M1-T8.
- **Exploit:** Ana's offer expires and the WO is re-offered to Marco. Ana (a past candidate) passes the gate, so the only thing standing between her and Marco's live offer is whatever M1-T8's compare-and-set checks. If the CAS is `WHERE state='PENDING' AND version=:v` without `current_contractor_id = :ana`, Ana accepts Marco's offer: a P0 identity bypass. The decline variant is quieter. Ana declines and `reoffer_next()` moves the offer *away from Marco* to rank 3 (griefing a competitor). The gate's decision also runs before `SELECT … FOR UPDATE`, which is a TOCTOU window. This breaks plan rule 2 ("No route does its own principal-vs-resource check").
- **Fix:** the gate returns a typed decision (`Allow(role=offeree|bound|owner)`, `Deny403`, `Deny404`, `Unavailable409(reason)`). A past candidate gets `Unavailable409` **from the gate**, with no dispatch mutation. For an offeree, dispatch re-asserts the binding **inside the lock**: the CAS predicate includes `dispatch.current_contractor_id = :principal_cid AND candidate.state = 'OFFERED' AND sla_deadline > now()`. On a miss it returns 409 and makes no state change, and in particular does not call `reoffer_next()`. Test: T-AUTH-9.

#### H-3 · Idempotency keys are globally scoped, so one user can collide with or replay another's
- **Location:** spec §4.4 `memory_events.idempotency_key unique`, `completion_reports.idempotency_key`; M1-T2, M1-T3, M2-T3, M2-T5, M2-T6; FR-6.4, FR-7.4.
- **Exploit:** "same key → same event" is implemented as a lookup by key alone. (a) Ana sends `transition` with a key Marco already used (visible in a shared device's logs, a support screenshot, or a weak client RNG). The server returns **Marco's** event, which is a cross-WO data leak, and silently drops Ana's request. (b) Key squatting: if Ana can predict or observe a key before Marco's queued submit flushes, she burns it, and Marco's offline completion is "deduplicated" into nothing. That loses completion data, which breaks NFR-5. (c) Same user, same key, different body: the server returns the old result and the contractor believes their corrected report was stored.
- **Fix:** an idempotency record is keyed by **(principal user_id, scope, key)**, where scope = route template + target id (e.g. `POST /workorders/{wo}/complete` + `wo`). Store a `request_hash` (SHA-256 of the canonical JSON body, or of the file digest for photos). A hit with the same hash returns the original response. A hit with a different hash → **422** (SPEC DELTA SD-2 for the code name). A lookup never crosses principals or scopes. `memory_events` keeps a unique constraint on `(actor_user_id, idempotency_key)` instead of a global one (clarification C-2). The photo route honors the key with the same scoping, so a queued retry doesn't duplicate uploads. Tests: T-IDEM-1.

#### H-4 · The CORRECTION (undo) chain is unconstrained
- **Location:** §5 `transition {action: undo, corrects_event_id?}`; FR-6.3; design §6.5; M1-T2, M2-T3.
- **Exploit:** `corrects_event_id` comes from the client. (a) Marco, bound to WO X, sends `undo` with the id of an event on Ana's WO Y. If the stage fold for Y collects corrections by `corrects_event_id` without filtering on `wo_id`, Ana's stage reverts. That corrupts another asset's immutable record through an endpoint the gate correctly authorized for X. (b) Undo of an undo (a "redo" that skips the confirm), or two concurrent undos of the same event, produce a fold that depends on ordering. (c) Undoing `EN_ROUTE` while `ARRIVED` is current leaves an impossible history. (d) An undo after completion rewrites a closed job's timeline.
- **Fix:** an undo is valid only if the target event is on **the same `wo_id`** (composite FK `(wo_id, corrects_event_id) → memory_events(wo_id, id)`), is a lifecycle **advance** (never a CORRECTION or an outcome/completion event), is the **latest uncorrected advance** on that WO, was authored by the same principal, and the WO is not completed. Otherwise → **409 `INVALID_TRANSITION`**. Add a partial `UNIQUE (corrects_event_id)` so an event can be corrected at most once, even under concurrency. Add `CHECK ((type = 'CORRECTION') = (corrects_event_id IS NOT NULL))`. If `corrects_event_id` is omitted, the server picks the latest uncorrected advance. `actor` and `at` always come from the principal and `app.clock`, never the body. The 10 s window stays UI-only, which is no behavior change. Test: T-LIFE-5.

#### H-5 · Append-only only holds if the app connects as a non-owner role, and the other write-once tables aren't covered
- **Location:** plan rule 3, M1-T2 (T-MEM-1); spec §4.3 `memory`, FR-7.4.
- **Exploit:** grants are bypassed by the table owner. If `DATABASE_URL` uses the role that ran migrations (the default in most compose setups), the app can `UPDATE`/`DELETE`/`TRUNCATE` `memory_events`. Any SQL-injection or ORM bug then rewrites history. T-MEM-1 can pass while this is true if it tests a separately created role. `completion_reports`, `calibration_records` and `workorders.failure_code` are append-only/set-once per FR-7.4 but have no DB-level control at all.
- **Fix:** two roles. The migrator owns the schema; the runtime role `insmartfix_app` is `NOSUPERUSER NOCREATEROLE`, does not own any table, and gets `INSERT, SELECT` only on `memory_events`, `completion_reports` and `calibration_records`. The migrator runs `REVOKE ALL … FROM PUBLIC` and sets no `ALTER DEFAULT PRIVILEGES` that grant `UPDATE/DELETE/TRUNCATE`. The settings use `DATABASE_URL` (runtime) and a separate `MIGRATION_DATABASE_URL`. A `BEFORE UPDATE` trigger on `workorders` raises if `OLD.failure_code IS NOT NULL AND NEW.failure_code IS DISTINCT FROM OLD.failure_code`; triggers bind even the owner. Test: T-MEM-2, which asserts against **the role the app's engine actually uses** (`current_user`).

#### H-6 · Dispatch create doesn't bind candidates or asset to the caller's tenant
- **Location:** M1-T6 `POST /dispatch/workorders`; FR-10.1; §5.
- **Exploit:** a Midtown owner posts `candidates: [{contractor_id: zed}]` (Zed is in another tenant), or `asset_id` of another tenant's asset. Zed's schedule now shows a Midtown WO, and accept returns Midtown's full pre-diagnostic packet, which is a cross-tenant data leak. Or the owner gets a WO wrapping another tenant's asset and reads its packet via the owner serializer. The gate's tenant check uses the WO's `tenant_id`, which would be the caller's, so it would not catch this.
- **Fix:** `asset_id` must belong to `principal.tenant_id`, or → 404. Every `candidates[].contractor_id` must exist in the same tenant, or → 422 (no detail on which id failed). The route requires role owner/FM (a contractor gets 403) and goes through the same structural coverage check (`dispatch_create` action). Test: T-DISP-4.

#### H-7 · Test-clock route guard is a deny-list on `ENV=production`
- **Location:** plan rule 6, M1-T3; TEST_PLAN §3 ("compiled out of production builds").
- **Exploit:** the route is mounted whenever `FAKE_CLOCK=1` and `ENV != production`. Staging is auto-deployed from `main`, internet-reachable and used for G2 evidence. Beta or any environment with `ENV` unset or misspelled also exposes it. If the route is reachable without auth (it has to be, for test harnesses), anyone can move server time. They can expire every offer at once (dispatch DoS), keep their own offer alive past its SLA, revive expired JWTs if token validation uses `app.clock`, and stamp arbitrary `at` values into the **immutable** memory log, where the damage can't be corrected.
- **Fix:** an allow-list. Mount only if `FAKE_CLOCK=1` **and** `ENV ∈ {local, test, ci}`. `ENV` has no default, so startup fails if it is unset. The app **refuses to start** if `FAKE_CLOCK=1` with any other `ENV`. Put the route in `app/testing/` and delete that package in the production Dockerfile stage, so "compiled out" is literally true. JWT `exp` is checked against the wall clock, never `app.clock`. The web proxy allow-list never includes `/__test/*`. Test: T-AUTH-18, which includes an image-level check.

### Medium

#### M-1 · `/contractor/{cid}` gives a contractor-id existence and tenant oracle
- **Location:** Plan §2.1 rows 2 and 4 (tenant check first, then 403); FR-1.4 ACs.
- **Exploit:** Marco probes `/contractor/{id}/schedule`. 403 means "a contractor in my tenant", 404 means "another tenant or nonexistent". With sequential ids this maps every competitor in his tenant and confirms which ids exist elsewhere.
- **Fix:** for a contractor principal, any `cid ≠ token.contractor_id` → **403** decided **before any lookup**, with an identical body whatever the target is. For owner/FM, a `cid` that doesn't exist or is in another tenant → identical **404**. Spec FR-1.4 lists both "other_id → 403" and "cross-tenant → 404" and they conflict for this case. This resolves the conflict in favor of 403 (clarification C-1). Test: T-AUTH-15.

#### M-2 · Not-yet-offered candidates count as "ever a candidate", and the nonexistent-WO case is missing
- **Location:** Plan §2.1 last row ("403 if ever a candidate, otherwise 404").
- **Exploit:** Ana is rank 3 on a WO that has only been offered to rank 1. She has no legitimate knowledge of it, but `transition`/`photo`/`complete` return 403 to her and 404 to everyone else. That oracle tells her which WOs she's queued for and confirms WO ids. The table also has no row for "WO does not exist", so implementations may diverge (500, 422, 404 with a different message).
- **Fix:** define the relationships precisely (plan §2.1). A **stranger** is no candidate row **or a candidate row that was never offered** (`QUEUED`). A nonexistent WO, a cross-tenant WO and a stranger WO all → the same 404 body. All 403 bodies are identical, and so are all 404 bodies: no "you are not a candidate" message. Covered by the expanded T-AUTH-6 matrix (new relationship rows) and T-AUTH-15.

#### M-3 · Gate coverage is checked too late and not structurally
- **Location:** plan rule 2; M2-T7 (route-introspection test lands after M1-T7 … M2-T6 have all merged).
- **Exploit:** six route-implementing PRs merge before anything mechanically checks that they call the gate. A handler that uses the path `cid`, or loads the WO by `wo` before calling `authorize`, is an IDOR that only human-style review would catch.
- **Fix (structural):**
  1. Gated routes are declared through a `gated_router()` factory whose `add_api_route` **requires** an `action=` argument and injects `Depends(gate(action))`. The dependency resolves the target and returns an `AuthorizedTarget` (principal + loaded contractor or WO row).
  2. Handlers receive `AuthorizedTarget` and **do not declare** `cid`/`wo` path parameters themselves, so they can't re-load by raw id.
  3. **T-AUTH-14**, moved to M1-T5, runs against the full route table, which already exists as M1-T1 stubs. It walks `app.routes`. Every `APIRoute` under `/v1/contractor`, `/v1/me/` (excluding exactly `GET /v1/me`), `/v1/workorders` and `/v1/dispatch` must have exactly one `GateDependency` in its dependant tree, with the `action` matching a checked-in `ROUTE_ACTIONS` map. The test fails on a route missing from the map, so a new route can't silently skip it. No gated handler signature may contain `cid` or `wo`. Every route not in a `PUBLIC_ROUTES` allow-list (`/v1/auth/login`, `/v1/healthz`, `/v1/readyz`) depends on `get_principal`.
  4. M2-T7 keeps the HTTP-level matrix and re-runs T-AUTH-14.

#### M-4 · Web BFF proxy: URL construction, header pass-through and CSRF
- **Location:** M4-T3; spec §4.2; FR-1.2, FR-1.4; design §13.
- **Exploit:** (a) If the upstream URL is built by string concatenation, e.g. `/v1/contractor/${cid}/` + the client path, then `..`, `%2e%2e`, `%2f` or an absolute URL in `[...path]` can retarget the request to another contractor's path, another host (SSRF) or `/__test/clock`. The API's own `cid == token` check is the only backstop. (b) Forwarding the client's `Authorization`, `Cookie`, `X-Forwarded-For` or `Host` headers lets a client pick the identity or the rate-limit key. (c) Cookie auth with `SameSite=Lax` still accepts same-site requests from any sibling subdomain, and older browsers with Lax-by-default quirks accept a top-level cross-site POST for two minutes after the cookie is set.
- **Fix:** the proxy matches the client path against an **allow-list of route templates** on decoded, normalized segments. It rejects anything containing `.`/`..` segments, encoded slashes, backslashes or a scheme. It **builds** the upstream URL from the template with `encodeURIComponent` on the one client-supplied id (`wo`). **Recommended:** forward to the `/v1/me/*` aliases so no `contractor_id` is ever interpolated. This is an implementation choice with identical observable behavior, not a spec change. The proxy sends only `Authorization: Bearer <cookie token>`, `Content-Type`, `Idempotency-Key`, `Accept` and a request id, and drops every other client header, including any client-sent `Authorization`. It sets the client IP for rate limiting from the platform's trusted header only (see M-7). Mutating requests (`POST/PUT/PATCH/DELETE`) require `Origin` (or `Sec-Fetch-Site: same-origin`) to match the app origin, or → 403. Tests: T-AUTH-7 (existing) and T-AUTH-17.

#### M-5 · JWT validation is under-specified
- **Location:** M1-T4; spec §4.3 (HS256, 12 h, claims `sub, role, tenant_id, contractor_id`).
- **Exploit:** a `jwt.decode` call without a pinned algorithm list is open to `alg: none` and to header-driven algorithm confusion in some library versions. Without `iss`/`aud`, a token minted by any other service sharing the secret (a reused env var) is accepted. Trusting `role`/`tenant_id`/`contractor_id` from the token for 12 h means a disabled user, or a contractor moved between companies, keeps full access until expiry.
- **Fix:** call `jwt.decode(token, key, algorithms=["HS256"], audience="insmartfix-api", issuer="insmartfix", options={"require": ["exp","iat","nbf","sub","iss","aud","jti"]})` with `leeway ≤ 30 s`. HS256 with a ≥ 256-bit secret from env is acceptable for a single-issuer, single-verifier system, so no change there. Fail startup on a weak or missing secret (already planned). `get_principal` loads the `users` row by `sub` and requires `disabled_at IS NULL` and `token_version == claim tv`. It takes `role`, `tenant_id` and `contractor_id` **from the DB row**, and a mismatch with the token → 401. This is one indexed PK read per request, well within NFR-1. Never log the token or the `Authorization` header (M1-T3 redaction). Test: T-AUTH-12.

#### M-6 · Sign-out does not revoke the token server-side — **SPEC DELTA SD-1**
- **Location:** FR-8.1 (sign out clears cookie/keychain); §5 has no logout route; NFR-6 "OWASP ASVS L1" (V3.3.1: logout invalidates the session).
- **Exploit:** a token captured before sign-out stays valid for up to 12 h: from a shared tablet's proxy logs, from a lost phone that was backed up, or from a BFF log mistake. Clearing the client copy doesn't help. NFR-6 claims ASVS L1, which this fails.
- **Fix:** add `POST /v1/auth/logout` (authenticated, 204) that increments `users.token_version`, which revokes every outstanding token for that user, using the mechanism from M-5. The web `/api/auth/logout` calls it and then clears the cookie. Mobile calls it before wiping the secure store, best effort when offline. This is an **additive contract change** → SD-1. **Interim until approved:** M-5's `token_version` check ships in M1-T4. Account disable also bumps the version, so an operator can revoke. Client-side clear stays as specified.

#### M-7 · Login rate limit is bypassable as designed
- **Location:** M1-T4 (`slowapi`, 5/min per IP+email); NFR-6; T-AUTH-8.
- **Exploit:** (a) `slowapi`'s default in-memory store is per process. With N workers or instances, the effective limit is 5N/min. (b) If the key uses `X-Forwarded-For` from any source, an attacker rotates that header for unlimited attempts. If it uses the socket peer, every web login comes from the BFF and shares one IP bucket. (c) `Marco@test.insmart.ai `, `marco@TEST.insmart.ai` and similar variants get separate buckets unless emails are normalized. (d) A per-IP+email key alone doesn't stop password spraying, where one password is tried across many emails from a botnet.
- **Fix:** use a shared store. Postgres is fine: an `auth_attempts` table or `pg` advisory counters. No Redis is needed. Use three limits, all evaluated before argon2:
  - per (normalized email, client IP): **5/min**, the spec's NFR-6 limit, unchanged;
  - per normalized email across all IPs: 20/hour, returning 429 rather than locking the account, to avoid a lockout DoS;
  - per client IP across emails: 30/min.
  "Client IP" comes from a header **only when the immediate peer is in `TRUSTED_PROXIES`** (the BFF or platform LB); the BFF sends the browser's IP in that header. Normalize emails with `strip().lower()` (NFKC) before keying and before lookup. 429 applies identically to existing and nonexistent emails. Tests: T-AUTH-8 (existing) and T-AUTH-11.

#### M-8 · Completion: double-complete race, set-once only in application code, mass assignment
- **Location:** M2-T5; FR-7.4, FR-7.5; §5 `CompletionReport`.
- **Exploit:** (a) Two devices, or the web queue plus a manual retry with a fresh key, submit concurrently. Both read "not completed" and both insert calibration and outcome events, so calibration is double-counted. This is exactly what T-COMP-5 says must not happen, and the queue's single-flight guarantee only holds per client. (b) The set-once rule lives in code paths, and a future admin script can overwrite `failure_code`. (c) Pydantic ignores extra fields by default. If a handler ever does `Model(**report.model_dump())` or `setattr` over the body, then `calibration_label`, `predicted_failure_code`, `actor`, `wo_id` or `technician_id` overrides become writable (mass assignment).
- **Fix:** take `SELECT … FOR UPDATE` on the WO's dispatch row at the start of the completion transaction. Insert `completion_reports` (PK `wo_id`) first. A unique violation → roll back everything → 409 `ALREADY_COMPLETED`, or the original response if the scoped idempotency record matches (H-3). The `failure_code` trigger comes from H-5. Every request model uses `model_config = ConfigDict(extra="forbid")`, so unknown fields → 422. The server alone computes `predicted_code` (from the snapshot, L-4), `label`, `actor` and `at`. Bounds: `parts_used` ≤ 50 items, `qty` 1–999, `description` ≤ 200, `technician_id` ≤ 120, `notes` ≤ 4000, JSON body ≤ 64 KB. `photo_ids` must each be a photo on **this** WO not already attached to a report, else → 422. Tests: T-COMP-8, T-COMP-9.

#### M-9 · Photo pipeline gaps
- **Location:** M2-T6; FR-7.7; §4.3 `media`.
- **Exploit:** (a) A decompression bomb, e.g. a 50 KB PNG declaring 60 000 × 60 000 px, or a crafted HEIC, exhausts API memory when Pillow decodes it. (b) Stripping only EXIF GPS leaves location in XMP, IPTC, PNG `tEXt`/`iTXt`/`eXIf` chunks and HEIC metadata boxes, plus device serials and owner names in other EXIF tags. (c) A polyglot (a valid JPEG header with an HTML/ZIP tail) passes a magic-byte sniff. It is harmless only if the stored object is the re-encoded output, never the upload bytes. (d) A compose or MinIO init that runs `mc anonymous set download` (common in examples), or an S3 bucket without Block Public Access, makes every job photo public by URL. (e) Unbounded uploads per WO exhaust storage, and Starlette's multipart parser accepts many parts.
- **Fix:**
  - Sniff magic bytes, then fully decode with `Image.MAX_IMAGE_PIXELS = 40_000_000` and `DecompressionBombWarning` treated as an error. Reject a long edge > 8192 px → 415 before decode allocation, using the header-only `Image.open().size`.
  - **Re-encode from pixels only.** Apply the EXIF orientation, then write a fresh file with no metadata at all (a superset of "GPS stripped", clarification C-4). Store **only** the re-encoded bytes, with a server-chosen `content_type`.
  - Enforce the 10 MB limit on the stream (count bytes while reading) and accept exactly one file part.
  - The object key is server-generated `wo/{wo}/{uuid4}`; discard the client filename.
  - The bucket is private with Block Public Access, and there is no anonymous policy in any environment's init. The app's S3 credentials are scoped to `PutObject`/`GetObject` on that bucket.
  - v1 has no photo-read route. When one is added, it must be gated by `authorize(get_wo)` and return a presigned GET with TTL ≤ 5 min.
  - Cap at 20 uploaded photos per WO, so a 21st → 413. The cap is a plan choice; 413 is already in the contract.
  - Keep `pillow-heif`/`libheif` pinned and covered by `pip-audit`.
  - Test: T-PHOTO-3.

### Low

| ID | Finding | Location | Exploit | Fix |
|---|---|---|---|---|
| **L-1** | Public ids may be sequential | §4.4 (`id` types unspecified) | Sequential WO, contractor and photo ids make M-1/M-2-style probing and volume inference trivial | All externally visible ids are UUIDv4 (`wo_id`, `contractor_id`, `photo_id`, `event_id`, `user_id`). M1-T2. |
| **L-2** | Cookie hardening beyond FR-1.2 | M4-T3 | A sibling subdomain can set a same-name cookie (cookie tossing) and pin a victim to an attacker session | Name it `__Host-ifx_session` (forces `Secure`, `Path=/`, no `Domain`), add `httpOnly; SameSite=Lax`, and set `Max-Age` equal to the JWT's remaining lifetime. Extend T-AUTH-4. |
| **L-3** | Enumeration parity outside the happy path | M1-T4; FR-1.1 | A disabled account, an account without a password hash, or a rate-limited unknown email returns a different code, message, header or latency class | Every failure → identical 401 `INVALID_CREDENTIALS` body and headers. The unknown-email path runs a dummy argon2 verify. A disabled user returns the same 401. Rate-limit parity from M-7. Test: T-AUTH-10. |
| **L-4** | Calibration compares against the prediction read at completion time | M2-T4, M2-T5; FR-7.5 | If the engine's packet for the asset changes between accept and completion (re-seed, later engine), the label is computed against a prediction the contractor never saw | Snapshot `predicted_failure_code` on the WO at dispatch create and accept (`workorders.predicted_failure_code`, insert-time) and label against the snapshot. Record `actor` on `calibration_records` so later trust-weighting can discount outliers. Outright bad-faith labeling by a bound contractor is out of v1 scope, noted for the ratings slice. |
| **L-5** | Free-text fields are stored XSS candidates for the future owner portal | M1-T8 (decline `note`), M2-T5 | `note`, `technician_id` and `parts_used[].description` are rendered later in Insmart Core | Length limits (decline `note` ≤ 500; others per M-8), stored as plain text, never rendered as HTML. React escaping covers v1 clients. |
| **L-6** | An expired-but-unswept offeree can still read the packet | Plan §2.1 `get_wo`; FR-5.2 | For up to 15 s after the SLA deadline, before the sweeper runs, the former offeree is still "current offeree" and can `GET /workorders/{wo}` | The gate classifies an offeree whose `sla_deadline ≤ now` as **past** (lazy expiry applied, or at least treated as past). Covered in the expanded T-AUTH-6 matrix. |
| **L-7** | CORS allow-list should be empty in production | M1-T3; NFR-6 | Neither client needs CORS: web goes server-to-server via the BFF and mobile is native. Any allowed origin is attack surface | Production `CORS_ORIGINS` is empty. `allow_credentials` is never combined with a wildcard. Local mock and dev origins come only from env. Unit test in M1-T3. |

---

## Assessment of the ten requested questions

1. **IDOR and enumeration.** Cross-tenant → 404 is right. Two oracles remain: contractor ids (M-1) and queued candidates (M-2). **Past candidate → 409 `OFFER_UNAVAILABLE` is acceptable.** A past candidate legitimately knew the WO existed, and `reason` (`expired|reassigned|withdrawn`) only tells them what the spec's toast already says. Conditions: the 409 body must not name or count other candidates, it must be produced by the gate without any dispatch mutation (H-2), and `get_wo` for a past candidate stays 404 so they can't keep reading the packet.
2. **Single `authorize()`.** The intent is right, but the plan enforces it only at the end of M2. M-3 gives a structural fix (router factory + `AuthorizedTarget` + route-table walk T-AUTH-14 moved into M1-T5).
3. **Path id vs token, `/me`, proxy.** The API must decide `cid ≠ token` → 403 before any lookup (M-1). `/me/*` must share the handler and gate (already planned). Owners without a `contractor_id` → 403 on `/me` actions (H-1). The proxy should forward to `/me/*`, build URLs from templates and strip client headers (M-4).
4. **JWT.** HS256 / 12 h / env secret ≥ 256 bits is acceptable. It needs alg pinning, `iss`/`aud`/`jti`/`nbf`, DB-backed claims and `token_version` (M-5). Server-side revocation on sign-out is an additive contract change (M-6, SD-1). Cookie flags are fine as specified, with an added `__Host-` prefix and `Max-Age` (L-2).
5. **Memory integrity.** The grants only work with role separation (H-5). The correction chain needs same-WO, latest-advance-only, no correction-of-correction, at-most-once and not-after-completion rules (H-4). Idempotency keys must be scoped per principal + route + target with a request hash (H-3). A contractor can't correct someone else's event once H-4's same-WO and same-actor rules hold, together with the gate's "bound contractor" check on `transition`.
6. **Completion.** Set-once needs a DB trigger (H-5). Repeat vs `ALREADY_COMPLETED` is correct semantically, but it needs a lock or unique-insert ordering to be race-free (M-8). Calibration poisoning by other parties is closed by H-1 (owners can't complete), H-2 (no offer theft) and M-8 (no mass assignment, server-computed label), and L-4 snapshots the prediction.
7. **Photos.** The plan covers sniff, 10 MB and EXIF GPS. It needs bomb limits, a full metadata strip, storing re-encoded bytes only, a private bucket with no anonymous policy in *any* env, a per-WO cap, and same-WO `photo_ids` (M-9, M-8). v1 has no photo-read route, so no signed URLs are exposed yet. The rule for when one is added is recorded in M-9.
8. **Test clock.** The deny-list is insufficient. It needs an allow-list plus a startup refusal plus removal from the production image (H-7).
9. **Login.** The message is already non-enumerating and the miss path is constant-time. The rate limit needs a shared store, trusted-proxy IP derivation, email normalization and per-email/per-IP caps (M-7), and the parity tests (L-3).
10. **Owner/FM scope.** Tenant-bounded is correct, but the plan lets owners act **as** a contractor. That must be restricted to read (H-1). Dispatch create must also be tenant-bounded on its inputs (H-6).

---

## SPEC DELTA items (to product-manager; reopen G1 for these deltas only)

| ID | Change | Why | Type | Interim behavior until approved |
|---|---|---|---|---|
| **SD-1** | Add `POST /v1/auth/logout` (authenticated, `204`): bumps `users.token_version`, revoking all of the user's outstanding tokens. Web `/api/auth/logout` and mobile sign-out call it. FR-8.1 AC gains "and the server session is revoked". | M-6; NFR-6 claims ASVS L1, and V3.3.1 requires logout to invalidate the session. | Additive contract route + AC addition | `token_version` check ships in M1-T4 (M-5), so account disable revokes. Sign-out is client-side only, as currently specified. |
| **SD-2** | Add error code `IDEMPOTENCY_KEY_REUSED` (HTTP 422) to every mutation that accepts `Idempotency-Key`: the same principal + scope + key with a different request body. | H-3(c): silently returning the old result for a different body loses the contractor's correction. | Additive error code | Return 422 with the generic validation-error envelope code, and never return the stored result for a mismatched body. |

### Spec clarifications (no change to approved behavior; product-manager to annotate the spec, non-blocking)

- **C-1 (FR-1.4):** a contractor requesting `/contractor/{id}/…` for any id other than their own gets **403**, whether that id exists, is in their tenant or is in another tenant. "Cross-tenant → 404" applies to resources looked up by owner/FM principals and to work orders. This resolves the two ACs that conflict for a contractor addressing another tenant's contractor id (M-1).
- **C-2 (§4.4):** `memory_events.idempotency_key` is unique **per actor** (`UNIQUE (actor_user_id, idempotency_key)`), and idempotency records are scoped by principal + route + target. FR-6.4/FR-7.4 semantics are unchanged for any single user (H-3).
- **C-3 (FR-1.4, design §13):** "owner/FM tenant-wide override" means **read** (`schedule`, `GET /workorders/{wo}`, dispatch state) in v1, exactly as §5's role column states. Owners cannot accept, decline, transition, upload or complete (H-1).
- **C-4 (FR-7.7):** "EXIF GPS stripped" is implemented as "all embedded metadata stripped after applying orientation", which is a strict superset (M-9).

---

## Test cases to add

Existing IDs that are **extended** are marked *(ext)*. New IDs are proposed here and are routed to the qa-engineer to add to TEST_PLAN §6. That is a test addition, not a requirement change, by the same route as plan note N3. The owning task is in the plan (§2.2 and §9.2).

| Test ID | Case | Covers | Platform | Owning task |
|---|---|---|---|---|
| **T-AUTH-6** *(ext)* | Matrix expected-status table regenerated from the **revised** §2.1. Owner same tenant × {accept, decline, transition, photo, complete} → 403. Add WO-relationship rows **stranger / queued candidate / offeree / offeree past deadline (unswept) / past candidate / bound / bound after completion / nonexistent WO**. Add principal "owner without contractor_id on `/me/*`". | H-1, M-2, L-6 | A | M1-T5 (policy), M2-T7 (HTTP) |
| **T-AUTH-9** | Past candidate cannot take or disturb a live offer: Ana's offer expires → re-offered to Marco → Ana `accept` → 409 `OFFER_UNAVAILABLE`, dispatch still PENDING for Marco, `version` unchanged. Ana `decline` → 409 and `reoffer_next` not called. Hypothesis-driven interleaving of gate check vs lock (offeree becomes past between gate and lock → 409, no bind). | H-2 | A | M1-T8 |
| **T-AUTH-10** | Login enumeration parity: unknown email, wrong password, disabled user, user with null hash → identical status, body and headers. The dummy argon2 verify is executed on the miss path (spy). 429 behaves identically for unknown and known emails. | L-3, FR-1.1 | A | M1-T4 |
| **T-AUTH-11** | Rate-limit bypass resistance: email case/whitespace/NFKC variants share a bucket; `X-Forwarded-For` from an untrusted peer is ignored; the per-email cap holds across 10 IPs; the per-IP cap holds across 40 emails; the limit holds across 2 app workers (shared store). | M-7, NFR-6 | A | M1-T4 |
| **T-AUTH-12** | JWT rejection: `alg: none`, `HS512`, RS/HS confusion header, missing `exp`/`sub`/`jti`, wrong `iss`/`aud`, `nbf` in the future, wrong secret, expired by wall clock while `app.clock` is set back, disabled user, stale `token_version`, token `role`/`tenant_id`/`contractor_id` differing from the DB row → 401. | M-5, H-7 | A | M1-T4 |
| **T-AUTH-13** | Logout revokes: after `POST /auth/logout`, the same token → 401 on `/me` and `/me/schedule`. Other tokens of the same user → 401. Web logout calls it and clears the cookie. **Lands after SD-1 is approved.** | M-6, SD-1 | A W | M1-T4 follow-up / M4-T11 |
| **T-AUTH-14** | Structural gate coverage: walk `app.routes`. Every `/v1/contractor`, `/v1/me/*` (except `GET /v1/me`), `/v1/workorders`, `/v1/dispatch` route has exactly one `GateDependency` whose `action` equals `ROUTE_ACTIONS[route]`. A route absent from the map fails. No gated handler declares `cid`/`wo` params. Every non-`PUBLIC_ROUTES` route depends on `get_principal`. | M-3, plan rule 2 | A | M1-T5 (re-run in M2-T7) |
| **T-AUTH-15** | No id oracles: Marco on `/contractor/{ana}`, `/contractor/{zed}` and `/contractor/{random uuid}` → byte-identical 403 bodies. Owner on another-tenant cid / nonexistent cid → identical 404. Contractor on nonexistent / cross-tenant / stranger / queued-candidate WO × every WO action → identical 404 bodies. | M-1, M-2 | A | M1-T5 |
| **T-AUTH-16** | Owner cannot act as contractor: owner same tenant on `/contractor/{marco}/accept\|decline/{wo}` and `/workorders/{wo}/transition\|photos\|complete` → 403 with no state change. Owner (no `contractor_id`) on `/me/schedule`, `/me/accept/{wo}`, `/me/decline/{wo}` → 403. | H-1 | A | M1-T5 (policy), M2-T7 (HTTP) |
| **T-AUTH-17** | BFF proxy hardening: `..`, `%2e%2e`, `%2f`, `\`, absolute-URL and `/__test/*` paths → 400/404, never forwarded. A client `Authorization`, `Cookie`, `X-Forwarded-For` or `Host` is not forwarded upstream (echo-server assertion). A cross-origin POST (bad `Origin` / `Sec-Fetch-Site: cross-site`) → 403. Upstream paths are only `/v1/me/*` or template-built. | M-4 | W | M4-T3 |
| **T-AUTH-18** | Test clock absent: with `ENV=production` and `ENV=staging`, the route table has no `/__test` path. Startup **fails** with `FAKE_CLOCK=1` and `ENV ∉ {local,test,ci}`, and with `ENV` unset. The production image lacks `app.testing` (`docker run … python -c "import app.testing"` exits non-zero, a CI step). | H-7 | A | M1-T3 (app), M0 follow-up (image step) |
| **T-AUTH-4** *(ext)* | Cookie is `__Host-` prefixed with `Max-Age` ≤ token lifetime. | L-2 | W | M4-T3 |
| **T-MEM-2** | Runtime role: the app engine's `current_user` is not the owner of any table and not a superuser. `has_table_privilege(..., 'UPDATE'/'DELETE'/'TRUNCATE')` is false on `memory_events`, `completion_reports`, `calibration_records`. A second write of `workorders.failure_code` raises, **even as the migrator role**. Bad `CHECK`s (`CORRECTION` without `corrects_event_id`, or vice versa) are rejected. | H-5, FR-7.4 | A | M1-T2 |
| **T-LIFE-5** | Correction rules: undo citing another WO's event → 409. Undo of a CORRECTION → 409. A second undo of the same event → 409, and two **concurrent** undos → exactly one succeeds. Undo of a non-latest advance → 409. Undo after completion → 409. `actor`/`at` in the body are ignored or rejected (`extra=forbid` → 422); stored values come from the principal and the clock. Ana's derived stage is unaffected by any of Marco's requests. | H-4 | A | M2-T3 |
| **T-IDEM-1** | Idempotency scoping: Ana reusing Marco's exact key on `transition`, `complete` and `photos` gets her own independent result and never Marco's event or body. The same user reusing a key on a different WO → independent request. The same user + scope + key + different body → 422 (SD-2 code once approved), and the stored result is not returned. The same everything → original response, with no second event, calibration or photo. | H-3 | A | M2-T3 (transition), M2-T5 (complete), M2-T6 (photos) |
| **T-COMP-8** | Concurrent completion with **different** keys from two sessions of the bound contractor (hypothesis, 100 iterations) → exactly one 200 and one 409 `ALREADY_COMPLETED`, exactly one `completion_reports` row, one `calibration_records` row and one outcome event. | M-8, FR-7.4/7.5 | A | M2-T5 |
| **T-COMP-9** | Mass assignment and bounds: a body with `calibration_label`, `predicted_failure_code`, `actor`, `wo_id` or `label` → 422 and nothing stored. Field bounds from M-8 → 422. `photo_ids` from another WO or already attached → 422. The label is computed against the dispatch-time snapshot (L-4) even if the engine's packet changed after accept. | M-8, L-4 | A | M2-T5 |
| **T-DISP-4** | Dispatch create is tenant-bounded: a candidate in another tenant → 422 (Zed's schedule unchanged). An asset in another tenant → 404. A contractor caller → 403. Unknown fields → 422. | H-6 | A | M1-T6 |
| **T-PHOTO-3** | Upload hardening: decompression-bomb PNG and oversized-dimension HEIC → 415, with memory bounded (RSS guard). A JPEG+HTML/ZIP polyglot is stored only as re-encoded bytes (stored digest ≠ upload digest, no trailing data). EXIF (all tags), XMP, IPTC, PNG text chunks and HEIC metadata are absent after upload. The client filename doesn't appear in the key. Anonymous GET on the stored object → 403 (MinIO in CI). Two file parts → 422. The 21st photo on a WO → 413. A non-bound contractor → 403/404 per §2.1. | M-9 | A | M2-T6 |

---

## Re-review triggers

The security-reviewer gate re-opens this review if a PR: adds a route under a gated prefix without updating `ROUTE_ACTIONS`; changes `identity_gate/policy.py`, the CAS predicate in `dispatch/accept.py` or `decline.py`, DB grants, triggers or roles, `app/testing/`, the BFF proxy allow-list, or JWT encode/decode; or adds any photo-read or signed-URL path.
