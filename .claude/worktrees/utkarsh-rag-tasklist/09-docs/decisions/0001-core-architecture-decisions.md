# ADR 0001 — Core Architecture Decisions

- **Status:** Accepted for RAG implementation — total-latency boundary confirmed by user on 2026-08-21; shared contract edits still require team review
- **Date:** 2026-08-18
- **Contract version affected:** v1 → v1.1
- **Scope:** latency contract, grounding semantics, JSON Schema composition/validation, embedding-model selection
- **Supersedes:** nothing
- **Follow-up ADRs reserved:** 0002 embedding model (frozen choice, post-benchmark) · 0003 chunking strategy · 0004 reranker keep/drop · 0005 Qdrant collection layout

This document resolves the four open architectural issues in `notes/CONTEXT.md` before implementation begins. No implementation code is written here.

Two findings that were not in the original four issues, surfaced while analysing them, are recorded in **Issue 3** and **Issue 4** respectively:

1. **All five WebSocket server events are currently unsatisfiable** — no JSON instance can validate against them. This is a live bug in `00-contracts/websocket-server-events.schema.json`, not a style question.
2. **Runtime JSON Schema validation does not belong in the request path** — it spends the very latency budget Issue 1 is about.

---

# Issue 1 — Latency contract

## 1. Issue

`answer.schema.json` defines `latency` as `total_ms` (required) plus nullable `embedding_ms`, `retrieval_ms`, `reranking_ms`, `generation_ms`.

The requirement is that "chunking + vector DB retrieval + everything through to final output" complete in under 200 ms. The user confirmed that this means the full online RAG path, including generation and grounding, with STT excluded. The contract therefore needs an end-to-end wall-clock SLO plus narrow stage timings for attribution.

Two separate questions are tangled here: **which metric should carry the target** (a measurement-semantics question) and **how the contract should express it** (a schema question). They have different answers.

## 2. Analysis

### Which metric carries the target

The four relevant measurements are STT, retrieval, generation, and total RAG wall-clock time. STT is excluded because it scales with audio duration and ends before the RAG request boundary. Retrieval and generation remain separately measured because they identify where time is spent, but neither is the product-level result.

The target belongs on **`total_ms`**, measured from validated RAG request entry through final serialized output. This preserves the literal user-visible requirement and prevents a fast retrieval stage from masking a slow generator or grounding check. It also makes provider latency an explicit architectural constraint: if a hosted generator cannot fit the measured budget, the implementation must change its model, hosting, output bound, caching, or interaction design rather than redefining the metric.

`retrieval_total_ms` remains useful as a wall-clock attribution segment covering embedding, vector search, and reranking. It is not the pass/fail SLO.

### How the contract should express it

Here the proposed direction should **not** be adopted as stated. Redefining `retrieval_ms` to mean `embedding + vector search + reranking` causes three concrete problems:

1. **Double counting.** `retrieval_ms` would overlap its siblings `embedding_ms` and `reranking_ms`. Any consumer that sums the component fields — a plausible reading of a flat latency object — gets a wrong number.
2. **Loss of the attribution we need.** No field would remain for bare vector-search time. When retrieval exceeds 200 ms, the first question is *which stage* — slow embedding, slow Qdrant, or slow reranking. Collapsing three stages into one destroys exactly the signal required to fix the thing the target exists to protect.
3. **It violates the contract's own rules.** `00-contracts/README.md`: "Do not modify an existing field, rename it, remove it, or change its meaning simply to make an implementation easier." Silently re-pointing a v1 field at a different quantity is the case that rule is written for.

The retrieval aggregate still needs a new name rather than a repurposed field. It should be **explicit and named**, not derived independently by the frontend, the evaluation harness, and the logger. `total_ms` carries the end-to-end SLO; `retrieval_total_ms` provides the nested retrieval-segment wall clock.

Three further gaps surfaced:

- **Grounding has no latency field.** `grounding` is a stage in the WebSocket `processing` enum and, per Issue 2, a real pipeline step that may involve an LLM call. Folding its cost into `generation_ms` would conflate our validator's cost with Sarvam's inference cost and defeat attribution. It needs its own field.
- **Totals should be wall-clock, not sums.** If `total_ms` is defined as the sum of components, orchestration overhead becomes invisible — it is the one cost that hides in the gaps between measured stages. Defining both totals as wall-clock over their segment makes overhead observable as the difference between the total and the sum of its parts.
- **TTFT.** Streaming is desirable but `generation_ms` must always mean time-to-final-token. Since `latency` is `additionalProperties: false`, adding a TTFT field later is a contract change requiring team sign-off and consumer updates; adding it now, while nothing is implemented, is free. A separate nullable field makes substituting TTFT for total generation latency structurally impossible rather than merely discouraged.

### Where STT latency is reported

Not in `answer.schema.json` — STT is not part of the RAG pipeline, and per `notes/CONTEXT.md` normalization belongs at the STT adapter boundary with no Transcript service. STT latency should be measured by the adapter and emitted to structured logs and metrics keyed by `request_id`.

That is sufficient for evaluation but **not** sufficient for the frontend's `Latency` component: the WebSocket `transcript` event carries only `{text, language, is_final}`, so STT timing cannot currently reach the UI. Options are to add `stt_latency_ms` to `transcript.schema.json` and the WS `transcript` event data, or to accept that the UI displays RAG latency only. **This is the backend and frontend owners' decision and is deliberately not decided here** — it does not block RAG work.

## 3. Decision

1. The **<200 ms target applies to the total RAG pipeline**, measured from the RAG request entry point through final serialized output. STT is excluded and measured separately.
2. `embedding_ms`, `retrieval_ms`, `reranking_ms` **keep their existing narrow, non-overlapping meanings**. `retrieval_ms` remains vector-search time alone.
3. Add **`retrieval_total_ms`** (required): wall-clock of the retrieval segment for attribution. It does not carry the project SLO; `total_ms` does.
4. Add **`grounding_ms`** (nullable).
5. Add **`generation_ttft_ms`** (nullable), populated only when streaming; `generation_ms` always means time-to-final-token.
6. `total_ms` and `retrieval_total_ms` are **wall-clock over their segments**. Components are not required to sum to their total; the difference is orchestration overhead and is expected to be visible. `total_ms` includes any online preprocessing/chunking, embedding, vector search, retrieval, reranking, context construction, generation, grounding/guardrails, and final serialization.
7. **STT latency is excluded from `answer.schema.json`** and reported via `request_id`-keyed logs and metrics. Surfacing it to the UI is deferred to the backend/frontend owners.
8. Benchmarks report P50, P70, P95, and P100. **P100 `total_ms` must remain below 200 ms** for the benchmark run to pass. No public artefact claims a latency result without naming the measurement it refers to.

## 4. Why this decision

It keeps the target on the complete user-visible RAG operation while preserving the stage attribution needed to diagnose misses. It adds three fields rather than redefining one, so no v1 field changes meaning and no consumer can double-count. It names the SLO once instead of letting consumers re-derive it, and it keeps hosted generation and grounding inside the budget where their real cost cannot be hidden.

## 5. Contract changes required

`00-contracts/answer.schema.json`, `$defs.latency` — add `retrieval_total_ms` (`number`, min 0) to `properties` and to `required`; add `grounding_ms` and `generation_ttft_ms` (`[number, null]`, min 0). Add descriptions fixing wall-clock semantics and the TTFT rule. Exact JSON in **Contract changes** below.

Not changed: `embedding_ms`, `retrieval_ms`, `reranking_ms`, `generation_ms`, `total_ms`.

## 6. Repository changes required

- `03-ai-rag-engine/observability/metrics.py` — per-stage timer producing the `latency` object; wall-clock segment timers for both totals.
- `03-ai-rag-engine/orchestration/pipeline.py` — owns segment boundaries so `retrieval_total_ms` is measured in one place, not summed by callers.
- `06-evaluation/metrics/latency.py` — percentile helpers for P50/P70/P95/P100, not mean-only reporting.
- `06-evaluation/benchmarks/latency.py` — asserts the target against P100 `total_ms`.
- `09-docs/evaluation/benchmark-results.md` — must state which measurement each figure refers to.

## 7. Testing / evaluation implications

Benchmarks report P50, P70, P95, and P100; **P100 is the pass/fail ceiling** because the selected requirement says the total pipeline should complete under 200 ms. Cold starts and steady state are reported separately. Retrieval must be benchmarked with the reranker both enabled and disabled, and generation plus grounding remain included in `total_ms`. A regression test should assert that component fields never exceed their enclosing total.

## 8. Risks and edge cases

- **Reranking is the budget's largest discretionary cost.** A cross-encoder is a second model in the hot path; if it does not fit, ADR 0004 removes it. `reranking_ms` is nullable precisely so this stays expressible.
- **An API-hosted embedding model puts a network hop inside the 200 ms budget.** This is a hard constraint on Issue 4's criteria, not a preference.
- **Cold start** — first-call model load must be excluded from steady-state figures and reported separately, or it will silently dominate p95 on a freshly started process.
- **Wall-clock totals include GIL contention and event-loop scheduling** under concurrency. Single-request benchmarks will look better than loaded ones; benchmark under concurrency or state clearly that figures are single-request.
- **Hosted generation may make the SLO infeasible.** That must appear as a failed benchmark and an architecture decision, not as a silent change from `total_ms` to retrieval-only latency.

---

# Issue 2 — Grounding and `grounded: false`

## 1. Issue

`answer.schema.json` requires a non-empty `answer` and a boolean `grounded`. The error enum also contains `GROUNDING_FAILED`. It is therefore ambiguous whether a failed grounding check produces an Answer with `grounded: false` or a transport-level error. The requirement is that a pipeline which ran successfully but produced insufficiently-supported output should be able to return `{answer, grounded: false, sources}` rather than an error, so the frontend's `Sources` component can show the evidence and flag low confidence.

## 2. Analysis

Collapsing this into a two-way split (success vs. failure) is what created the ambiguity. There are **three** distinct outcomes, and they differ in whether evidence exists and whether the pipeline completed:

**Outcome 1 — no usable evidence retrieved.** Retrieval returns nothing above the relevance floor. There is nothing to generate from, and generating anyway is an invitation to hallucinate. The LLM is not called.

This should be the existing **`NO_RELEVANT_CONTEXT`** error rather than an Answer with `grounded: false` and empty sources. The reason is not that the pipeline failed — it did not — but that `answer` requires `minLength: 1`, so returning an Answer would force the RAG engine to synthesise user-facing "I could not find anything" prose. That prose would have to exist **in all eleven languages**, putting localised UI copy inside the retrieval engine. That is a genuine design smell and a translation burden in a system whose defining constraint is *no translation layer*. Returning an error code and letting the frontend render its own localised empty state keeps user-facing copy where it belongs. It also gives `NO_RELEVANT_CONTEXT` a real meaning instead of leaving it dead code.

**Outcome 2 — evidence retrieved, answer generated, grounding check not satisfied.** This is the case the requirement is about, and it is **not a failure**. Retrieval worked, generation worked, and we have both prose and the sources it was supposed to rest on. Suppressing that behind an error throws away the most useful thing the UI could show: the answer *next to* the evidence, marked as weakly supported. This is an **Answer with `grounded: false`**, sources populated, followed by `complete(status: "success")`.

**Outcome 3 — a stage malfunctioned.** Vector DB unreachable, LLM timeout, or the grounding validator itself threw. This is an error.

Which code for outcome 3? Keeping `GROUNDING_FAILED` for "the validator malfunctioned" is a naming trap: the name reads as "the answer failed grounding", which is outcome 2 — the case we have just decided is *not* an error. Retaining the code with an inverted meaning preserves the exact ambiguity this issue asks to remove.

`RAG_ERROR` already means "a stage of the RAG pipeline failed". A validator crash is not semantically special enough to need its own code, and dedicated enum members are a poor diagnostic channel compared with `request_id`-keyed structured logs, which `03-ai-rag-engine/observability/logger.py` provides and contract rule 5 already mandates. `GROUNDING_FAILED` therefore earns nothing and costs clarity. Removing it beats renaming it, and beats inventing a new code — consistent with the instruction not to add status fields where existing semantics suffice.

**One edge case resolves cleanly under a precise definition of `grounded`.** If the grounding validator *times out*, we hold a fully generated answer but cannot assert it is supported. Discarding it as `RAG_ERROR` wastes the entire generation cost and helps nobody. Defining:

> `grounded: true` — verified as supported by the returned sources.
> `grounded: false` — **not verified**: either checked and found unsupported, or unverifiable.

makes "validator timed out" honestly representable as `grounded: false`, with no new field. Only a hard malfunction with no answer in hand becomes `RAG_ERROR`. This definition is the whole reason no additional status field is needed.

**No change to `answer` or `grounded` is required.** The concern that `minLength: 1` makes `grounded: false` unreachable only holds if grounding failure implies *no answer*. Under this decision, outcome 2 always has generated prose, so `minLength: 1` is satisfied naturally. The constraint is doing useful work: it is what forces outcome 1 to be an error rather than a synthesised multilingual apology.

## 3. Decision

| Outcome | Condition | Emitted |
|---|---|---|
| 1 | No evidence above relevance floor; LLM not called | `error: NO_RELEVANT_CONTEXT` → `complete(failed)` |
| 2 | Retrieval + generation succeeded; support not verified | `answer` with `grounded: false`, sources populated → `complete(success)` |
| 3 | A stage malfunctioned | `error: RAG_ERROR` (or `RAG_TIMEOUT`) → `complete(failed)` |

1. **`grounded: false` is a valid, expected Answer state**, not an error.
2. **`grounded` means "verified supported"**; `false` covers both *unsupported* and *unverifiable*.
3. **`GROUNDING_FAILED` is removed** from the error enum (10 codes → 9). Validator malfunction → `RAG_ERROR`.
4. **`NO_RELEVANT_CONTEXT`** is reserved for outcome 1 and implies no LLM call.
5. **Grounding-validator timeout → `grounded: false`**, not an error, when an answer is in hand.
6. **No new fields.** `grounded` plus `sources[].score` is sufficient for the UI.
7. `answer.schema.json` is unchanged apart from clarifying the `grounded` description.

## 4. Why this decision

It resolves the ambiguity at the root — by deleting the code whose name conflicts with the semantics — rather than layering a clarification on top of it. It keeps localised user-facing copy out of the RAG engine, which matters disproportionately in an eleven-language system with no translation layer. It preserves the demo's most persuasive view: answer beside evidence, honestly labelled. And it adds nothing: three outcomes are expressed with one existing boolean and two existing error codes.

## 5. Contract changes required

- `00-contracts/websocket-server-events.schema.json` — remove `GROUNDING_FAILED` from `$defs.error.data.code`.
- `00-contracts/answer.schema.json` — clarify the `grounded` description only. No structural change.
- `00-contracts/README.md` — update the error-code list; document the three outcomes.

## 6. Repository changes required

- `03-ai-rag-engine/guardrails/relevance.py` — relevance floor; decides outcome 1 **before** generation.
- `03-ai-rag-engine/guardrails/grounding.py` — sets `grounded`; hard timeout whose expiry yields `grounded: false`.
- `03-ai-rag-engine/orchestration/errors.py` — maps internal failures to the 9 remaining codes.
- `03-ai-rag-engine/generation/prompts.py` — instructs the model to decline when context is thin, in the query's language.
- `06-evaluation/metrics/grounding.py` — **new**; grounding treated as a classifier.

## 7. Testing / evaluation implications

Grounding becomes a **measurable classifier, not a gate**, and needs precision/recall against labelled `(answer, context, is_supported)` triples.

The **`grounded: false` rate** must be tracked as a first-class metric, because both extremes are silent failures: a rate near zero means the validator is toothless and rubber-stamping hallucinations; a very high rate means retrieval or the prompt is broken. Neither is visible without the metric, and both look like "working" in a demo.

The rate must be broken down **per language**. A lexical-overlap grounding check behaves very differently across agglutinative Malayalam or Tamil and Devanagari Hindi; a single aggregate will hide a validator that effectively fails for a subset of users. Evaluation lives in `06-evaluation/benchmarks/end_to_end.py` using the new metrics module.

## 8. Risks and edge cases

- **Highest-severity risk:** retrieval returns superficially similar chunks that clear the relevance floor without containing the answer; generation produces fluent unsupported prose. Grounding is the only remaining defence, and its per-language reliability is therefore load-bearing.
- **If grounding uses an LLM call**, it adds a second inference to every request after generation has already been paid for. `grounding_ms` (Issue 1) exists to make that cost visible.
- **The relevance floor is a tuned threshold**, not a natural constant. Its value must come from the Issue 4 benchmark and be recorded, or it becomes an undocumented magic number that determines how often users see `NO_RELEVANT_CONTEXT`.
- **Frontend contract:** `grounded: false` arrives with `complete(status: "success")`. The UI must not treat it as an error path — worth stating explicitly to the frontend owner.
- Score scales are not comparable across embedding models, so the floor must be re-tuned if ADR 0002 changes the model.

---

# Issue 3 — JSON Schema references

## 1. Issue

`websocket-server-events.schema.json` references `"$ref": "answer.schema.json"` while declaring `$id: https://echoquery.dev/contracts/websocket-server-events.schema.json`. The concern is that the relative reference resolves against the `$id` base and that validators may require both schemas to be explicitly loaded. The requirement is standards-compliant schemas with no duplication of the Answer contract, a defined local validation story, and no custom schema registry.

## 2. Analysis

### The reference itself is already correct

Under JSON Schema 2020-12, a relative `$ref` resolves against the current base URI, which is the enclosing `$id`. So `"answer.schema.json"` resolves to `https://echoquery.dev/contracts/answer.schema.json` — precisely the Answer schema's `$id`. **No schema change is needed.** The relative form is also preferable to spelling out the absolute URI: both resolve identically, but the relative form follows automatically if the `$id` base is ever changed, and it does not repeat the base in five places.

The real requirement is a **tooling** one: the validator must have all five schemas registered by `$id`, with remote fetching disabled. `echoquery.dev` is an identifier, not a location — it very likely does not serve these files, so a validator left in fetch-enabled mode would fail confusingly or, worse, hang in CI. Fetching must be **off by design**, not merely unused.

This does not require a custom registry. `referencing.Registry` — the standard mechanism paired with Python's `jsonschema` for 2020-12 — is exactly the intended tool. Using a library's built-in registry is not the "custom schema registry" to be avoided; hand-rolling `$ref` resolution would be.

Bundling the Answer schema into the WebSocket schema's `$defs` was considered and rejected: it duplicates the Answer contract, which contract rule and the no-duplication requirement both forbid.

### Finding: all five server events are currently unsatisfiable

While confirming the reference resolves, a live bug surfaced. Each event is composed as:

```json
"transcript": {
  "allOf": [
    { "$ref": "#/$defs/base" },
    { "type": "object",
      "additionalProperties": false,
      "properties": { "type": {...}, "data": {...} },
      "required": ["type", "request_id", "timestamp", "data"] }
  ]
}
```

`additionalProperties` is evaluated **against the `properties` of its own schema object only**. It does not see `properties` contributed by a sibling `allOf` branch or through a `$ref`. The second branch declares only `type` and `data`, so when a real event arrives:

```json
{ "type": "transcript", "request_id": "...", "timestamp": "...", "data": {...} }
```

branch 1 (`base`) passes, but branch 2 rejects `request_id` and `timestamp` as additional properties. The same branch simultaneously *requires* those two fields and *forbids* them. **No instance can validate.** This affects all five events — `transcript`, `processing`, `answer`, `error`, `complete` — so the entire server-event contract is currently unusable.

`websocket-client-events.schema.json` is unaffected: it uses no `allOf`, and each event declares all of its properties locally.

This is the classic `allOf` + `additionalProperties` interaction, and draft 2020-12 added the fix. `unevaluatedProperties` **does** consider annotations produced by `allOf` and `$ref`. Placing `"unevaluatedProperties": false` at the event level, as a sibling of `allOf`, keeps `base` DRY while restoring strictness. The schemas already declare 2020-12, and both Python `jsonschema` (`Draft202012Validator`) and Ajv support the keyword.

The alternative — inlining `request_id` and `timestamp` into all five events and deleting `base` — also works and is simpler to reason about, at the cost of repeating two fields five times and losing the single definition of the event envelope. Given 2020-12 is already in use and provides the correct keyword, keeping `base` is preferable.

That this bug survived into a committed contract is itself the argument for the validation tooling below: **validating one example instance per contract would have caught it immediately.**

### Finding: runtime schema validation does not belong in the request path

Contract rule 6 requires validation at boundaries. Read naively, that means validating every Answer against `answer.schema.json` at runtime — which spends the latency budget Issue 1 is built around, on every single request.

The contracts README already implies the better arrangement: JSON Schema → Pydantic models. That gives:

- **Runtime:** Pydantic models at boundaries. Fast, and needed anyway for FastAPI.
- **CI and tests:** JSON Schema validation proves the Pydantic models still match the contracts, by validating serialised fixtures against the schema set.

This satisfies rule 6 more strongly than per-request validation — an equivalence proven once in CI is a stronger guarantee than a check that can be disabled under load — and it keeps the hot path clean.

One consequence needs the backend owner's agreement. If both `01-backend-api` and `03-ai-rag-engine` define Pydantic models for Query and Answer, that duplicates an interface, which the contracts README forbids. The natural split: **the RAG engine owns the Query / Answer / Source / Latency models**, since it consumes one and produces the other, and the backend owns the WebSocket **envelope** models that embed the RAG Answer model. The backend already imports the RAG pipeline to call it, so importing its models introduces no new coupling, and contract rule 2 constrains only the *frontend*. **Recommended, not decided here.**

## 3. Decision

1. **Keep `"$ref": "answer.schema.json"`** — relative form, unchanged. It is already standards-compliant.
2. **No duplication or bundling** of the Answer schema.
3. **Fix the `allOf` bug:** in each of the five server events, remove `additionalProperties: false` from the inner branch and add `"unevaluatedProperties": false` as a sibling of `allOf`. Reduce the branch's `required` to `["data"]`, since `base` already requires `type`, `request_id`, `timestamp`.
4. **Validation tooling:** load all of `00-contracts/*.schema.json` into a `referencing.Registry` keyed by `$id`, with **remote retrieval disabled**. No custom resolver.
5. **Add `07-scripts/validate_contracts.py`** — CI-facing: asserts each file is a valid 2020-12 schema, that every `$ref` resolves locally, and that example instances validate. Must fail on any attempted network fetch.
6. **Add `00-contracts/examples/`** — at least one valid instance per contract, plus one deliberately-invalid instance per contract to prove the schema actually rejects.
7. **Runtime uses Pydantic; CI uses JSON Schema** to prove equivalence. No per-request schema validation in the pipeline.
8. **Recommended to the backend owner:** RAG owns Query/Answer models; backend owns WS envelopes embedding them.

## 4. Why this decision

It changes the contract only where it is actually broken, and leaves the reference — which was already right — alone. It uses the keyword 2020-12 added for exactly this composition problem, so `base` stays as the single definition of the event envelope. It puts schema validation in CI, where it is a proof, rather than in the request path, where it would be a tax on the budget Issue 1 defends. And it adds example instances, which convert this class of bug from "discovered during integration" into "caught on commit".

## 5. Contract changes required

- `00-contracts/websocket-server-events.schema.json` — `unevaluatedProperties` fix across all five events; remove `GROUNDING_FAILED` (Issue 2). Exact JSON below.
- `00-contracts/examples/` — new directory of instances.
- No change to the `$ref`, to `answer.schema.json`'s structure, or to the client-events schema.

## 6. Repository changes required

- `07-scripts/validate_contracts.py` — new.
- `03-ai-rag-engine/tests/test_contracts.py` — new; asserts Pydantic output validates against `answer.schema.json`.
- Dependency manifest — `jsonschema` and `referencing` as dev dependencies.
- CI/pre-commit wiring for `validate_contracts.py` (coordinate with the infrastructure owner).

## 7. Testing / evaluation implications

The negative examples matter as much as the positive ones: a schema that accepts everything passes a positive-only suite. The suite must also assert that an unknown property is rejected — the specific regression that `unevaluatedProperties` fixes. Round-trip tests (Pydantic → JSON → schema validation) are what keep the models and contracts from drifting once implementation is under way.

## 8. Risks and edge cases

- **`unevaluatedProperties` has weaker support in older validators.** Both current `jsonschema` and Ajv handle it; pin versions and let CI catch a downgrade.
- **The frontend consumes these contracts as TypeScript types.** If types are generated from JSON Schema, the generator must also support `unevaluatedProperties` — flag to the frontend owner.
- **`oneOf` across five events is safe** only because each `type` is a distinct `const`. Adding an event without a unique `const` would make more than one branch match and produce a confusing failure.
- **CI must have no network access to `echoquery.dev`,** or a fetch-enabled validator could appear to pass for the wrong reason.
- **`sources[].metadata` is `additionalProperties: true`** by design — an intentionally open bag. It will not catch metadata typos, so metadata keys need a convention documented elsewhere.

---

# Issue 4 — Stack and embedding-model selection

## 1. Issue

The stack is frozen: FastAPI, WebSocket, Sarvam Saaras v3 (production STT), Voxtral Mini (testing STT), Sarvam-105B, Qdrant, React + Vite + TypeScript. The remaining significant ML decision is the **multilingual embedding model**, which must not be chosen arbitrarily. Required: selection criteria, whether to benchmark first, what benchmark, deciding metrics, where it lives, and what to record. Plus a consistency check on the rest of the stack.

## 2. Analysis

### Criteria must be written before candidates are examined

Otherwise the criteria get shaped by whichever model was going to be picked anyway. Nine criteria, in priority order:

1. **Genuine coverage of all eleven locales.** Devanagari, Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Gurmukhi, Odia, Latin. A hard filter — a model missing one locale fails, regardless of aggregate scores. Odia is the usual gap in nominally multilingual models and must be verified specifically rather than assumed from a "100+ languages" claim.
2. **Cross-lingual alignment.** This is the most important criterion and the easiest to overlook. Because there is **no translation layer**, a Hindi query must retrieve relevant English chunks — and for MSME and government content, a large share of the corpus will be English. That requires a genuinely *shared* embedding space, not eleven separately-competent monolingual capabilities. A model can score well per-language and still be useless here.
3. **Trained for retrieval**, i.e. asymmetric short-query → long-passage search, not only sentence similarity. STS-trained models degrade noticeably on this shape of task.
4. **Latency and footprint.** Embedding must leave room inside the 200 ms total RAG budget for Qdrant search, reranking, generation, grounding, and orchestration. This constrains parameter count and sequence length, and decides CPU versus GPU.
5. **Dimensionality.** Drives Qdrant memory and search speed. Matryoshka-capable models are advantageous: dimensionality can be traded for speed without re-embedding the corpus.
6. **Maximum sequence length.** Must accommodate the chunk size chosen in the chunking phase — the two decisions are coupled and cannot be frozen independently.
7. **License and hosting.** **An API-hosted embedding model places another network round trip inside the 200 ms total budget.** This is close to disqualifying; strongly prefer a locally-served model.
8. **Tokenizer efficiency on Indic scripts.** A tokenizer that fragments Indic text inflates token counts, raising latency and shrinking effective context. Measurable, and routinely ignored.
9. **Qdrant compatibility.** Trivial for any dense vector, but the configured distance metric must match what the model was trained for (cosine vs. dot).

### Benchmarking is required, not optional

`notes/CONTEXT.md` principle 6 demands decisions be resolved by reasoning or benchmarking rather than silent choice, and this decision cannot be settled from published aggregates. Public multilingual leaderboards do not cover this corpus, this domain, or cross-lingual query→passage retrieval across these particular eleven locales. Published averages also mask per-language variance — exactly the variance that determines whether Odia and Malayalam users get a working product.

**No performance figures are asserted anywhere in this document.** The benchmark produces them.

### Benchmark design

Freeze one chunking configuration as the control so the embedding model is the only variable; the chunking sweep happens later, against the frozen model.

The evaluation set is `06-evaluation/datasets/queries.json`, each item carrying `query`, `query_language`, `relevant_chunk_ids[]`, and a `cross_lingual` flag. It must cover all eleven locales under two conditions: monolingual (query language = chunk language) and cross-lingual (query language ≠ chunk language, with emphasis on X→English).

Labelling by hand across eleven languages is not feasible at hackathon pace. The practical route is LLM-assisted generation: given a chunk, have Sarvam-105B write a question answerable from it in language *L*, yielding a `(query, gold chunk)` pair; generate cross-lingual pairs by writing the question in a language other than the chunk's.

This carries a **known bias that must be recorded rather than glossed**: questions generated from a chunk tend to mirror its vocabulary, which inflates scores for lexically-oriented models and understates the advantage of semantically stronger ones. Mitigations: an explicit paraphrase step, and human spot-checking of a sample per locale. The bias is acceptable for *ranking candidates against each other* — it applies roughly equally to all of them — but the absolute numbers should not be published as retrieval quality.

### Deciding metrics

**Primary: Recall@`fetch_k`** — recall at the candidate count actually handed to the reranker. With a reranker downstream, the embedding model's job is candidate *recall*; final ordering is the reranker's. Optimising nDCG@5 on the retriever would be tuning the wrong stage. If ADR 0004 drops the reranker, the primary metric moves to nDCG@10.

**Secondary:** nDCG@10 and MRR@10, as insurance against the reranker being dropped.

**Reported separately, never averaged together:** cross-lingual and monolingual performance. An aggregate mean can hide a model that is strong monolingually and unusable cross-lingually — which is disqualifying here, because the no-translation-layer decision makes cross-lingual retrieval load-bearing.

**Per-locale breakdown, with the worst locale called out.** The decision rule uses a floor on the *worst* locale, not the mean; a mean-optimal model that collapses on two languages ships a broken product for those users.

**Latency:** p50/p95 single-query embedding time on target hardware, plus corpus-embedding throughput for index build cost.

**Decision rule, fixed before the benchmark runs** — this is what makes the outcome defensible rather than post-hoc:

1. **Gate** — all eleven locales supported; worst-locale Recall@`fetch_k` at or above an agreed floor; embed P95 leaves measured room for every later stage inside the 200 ms total budget.
2. **Rank survivors** by cross-lingual Recall@`fetch_k`.
3. **Tie-break** by lower p95, then smaller dimensionality.

The floor in step 1 must be agreed by the team from the observed monolingual baseline once the harness runs. It is deliberately not given a number here, because inventing one would be exactly the arbitrary choice this issue exists to prevent.

### Rest of the stack

Runtime services: the FastAPI app, Qdrant, and external Sarvam APIs. **One added service.** No Redis, no separate reranker service (it runs in-process), no queue. Internally consistent and appropriately minimal.

Consistency points worth recording:

- **Sarvam-105B is reached over the network,** so generation latency includes RTT and is outside our control — independently reinforcing Issue 1.
- **Single-vendor concentration:** both STT and the LLM are Sarvam. Voxtral Mini backs up STT; there is **no LLM fallback**. Noted as a risk, not a redesign — swapping the LLM mid-hackathon would violate the stability principle, and the pipeline's `RetrievedContext` boundary means retrieval survives an LLM outage.
- **Qdrant must be added to `08-infrastructure/compose/*`** (currently empty). The RAG engine depends on it; the file belongs to the infrastructure owner. Coordination item.
- **The stack is not yet expressed as pinned dependencies** — no `pyproject.toml` or `requirements.txt` exists. Until it is, "decided" and "reproducible" are different things, which is the TBD-after-implementation risk `notes/CONTEXT.md` warns about.

### Repository placement

Candidate adapters belong **in the benchmark, not in `provider.py`**. `embeddings/base.py` defines the protocol candidates implement; `embeddings/provider.py` carries only the frozen winner. Production code therefore never accumulates dead abstractions for models that lost — avoiding the unnecessary-abstraction outcome the principles warn against.

`06-evaluation/results/` is **gitignored**, so a results summary must be committed into the ADR itself or the evidence for the decision is lost.

## 3. Decision

1. **Do not freeze the embedding model in this ADR.** It is decided by benchmark, recorded in **ADR 0002**.
2. Adopt the nine criteria, with locale coverage and cross-lingual alignment as gates.
3. **Strongly prefer a locally-served model**; an API-hosted embedder is near-disqualifying on criterion 7.
4. Build the labelled eval set at `06-evaluation/datasets/queries.json`, LLM-assisted with human spot-checks, covering all eleven locales in both conditions, with the generation bias recorded.
5. **Primary metric: Recall@`fetch_k`.** Report cross-lingual and monolingual separately, with a per-locale breakdown and the worst locale named.
6. Fix the gate/rank/tie-break decision rule **before** running.
7. Placement: harness `06-evaluation/benchmarks/embeddings.py` (new); metrics reuse `06-evaluation/metrics/retrieval.py` and `latency.py`; CLI `07-scripts/benchmark.py`; candidate adapters in the benchmark; winner only in `embeddings/provider.py`.
8. **Commit a results summary into ADR 0002**, since `06-evaluation/results/` is gitignored.
9. Rest of stack confirmed consistent and minimal. Record the single-vendor risk; add Qdrant to compose; add a dependency manifest.
10. Adopt `NNNN-title.md` for `09-docs/decisions/`.

## 4. Why this decision

It puts the criteria and the decision rule on record *before* the numbers exist, which is the difference between a benchmark that decides something and a benchmark that ratifies a choice already made. It measures the property the architecture actually depends on — cross-lingual retrieval, which the no-translation-layer decision makes load-bearing — instead of a leaderboard average that would hide it. It sets the primary metric at the stage boundary that matters, candidate recall feeding the reranker. It gates on the worst locale, so the product does not quietly fail for speakers of two of its eleven languages. And it keeps losing candidates out of production code.

## 5. Contract changes required

**None.** The embedding model is an internal implementation detail; no contract exposes vectors or model identity. That this decision requires no contract change is a sign the retrieval boundary is drawn correctly.

## 6. Repository changes required

- `06-evaluation/benchmarks/embeddings.py` — **new**; candidate sweep.
- `06-evaluation/datasets/queries.json` — populate (currently 0 bytes).
- `06-evaluation/metrics/retrieval.py` — Recall@k, MRR@k, nDCG@k.
- `07-scripts/benchmark.py` — CLI entry point.
- `03-ai-rag-engine/embeddings/base.py` — embedder protocol; `provider.py` — winner only.
- `03-ai-rag-engine/config/settings.py` — model id, dimensionality, `fetch_k`, `top_k`, relevance floor.
- `.env.example` — populate (currently 0 bytes): Sarvam key/base URL, Qdrant URL, model ids.
- `pyproject.toml` / `requirements.txt` — **new**; pin the stack.
- `09-docs/decisions/0002-embedding-model.md` — after the benchmark, with committed results.
- `08-infrastructure/compose/docker-compose.dev.yml` — add Qdrant (**infrastructure owner**).

## 7. Testing / evaluation implications

The eval slice must be held out of the index, or Recall@k measures memorisation. The corpus is fixed across candidates, so it supplies negatives; no separate hard-negative mining is needed for Recall@k. Each candidate needs its own throwaway index — build cost is part of the benchmark's runtime and worth measuring, since it recurs on every re-index. Embedding latency must be measured on the same hardware class as deployment, or the 200 ms gate is meaningless. Cold-start model load is excluded from steady-state figures and reported separately.

## 8. Risks and edge cases

- **LLM-generated queries lexically mirror their source chunk.** The single largest threat to the benchmark's validity. Mitigated by paraphrasing and spot-checks; the bias must be stated wherever the numbers appear.
- **Chunking and maximum sequence length are coupled**, so the "freeze chunking as control, then sweep models" order is a deliberate simplification. If the winner's sequence limit conflicts with the control chunking, the sweep needs one more pass — an accepted cost of not sweeping both dimensions at once.
- **A model can pass the locale gate on tokenizer coverage while being badly under-trained on a language.** Coverage is necessary, not sufficient; the per-locale Recall breakdown is what actually detects this.
- **Similarity scores are not comparable across models**, so the relevance floor from Issue 2 must be re-tuned whenever the model changes. Recording the floor alongside the model in ADR 0002 keeps the two coupled.
- **Reranker latency competes with embedding latency** inside one shared budget; ADR 0004 cannot be decided before this benchmark exists.
- **Odia is the likeliest gate failure.** If no candidate clears it, the escalation is an explicit, recorded decision — degraded support for that locale, or `UNSUPPORTED_LANGUAGE` for it — never a silent quality gap.

---

# Frozen architecture

```
                    ┌──────────────── binary audio frames ────────────────┐
                    │                                                     ▼
Frontend  ──WS client events──►  FastAPI  ──►  STT Adapter (Sarvam Saaras v3 │ Voxtral Mini)
(React+Vite+TS)                    │                        │
      ▲                            │              normalize in the adapter
      │                            │                        ▼
      │                            │            Transcript  (data contract, NOT a service)
      │                            │                        │
      │                            ◄────────────────────────┘
      │                            │
      │                            ▼
      │                        Query  (query.schema.json)
      │                            │
      │                            ▼
      │              ┌─────────  RAG Engine  ─────────────────────────────┐
      │              │                                                    │
      │              │  input_guard  →  UNSUPPORTED_LANGUAGE              │
      │              │      ▼                                             │
      │              │  ┌──── total_ms: all stages (<200 ms at P100) ──┐ │
      │              │  Embedding  →  Qdrant search  →  Reranking       │ │
      │              │      └── retrieval_total_ms (attribution) ──┘    │ │
      │              │      ▼                                             │
      │              │  RetrievedContext ──┬──► retrieval-only evaluation │
      │              │      │              │                              │
      │              │  relevance ─ empty ─┴──► NO_RELEVANT_CONTEXT       │
      │              │      ▼                                             │
      │              │  Sarvam-105B  (generation_ms, measured separately) │
      │              │      ▼                                             │
      │              │  Grounding  →  grounded: true | false              │
      │              │      ▼                                             │
      │              │  Answer + final serialization                   ─┘ │
      │              └────────────────────────────────────────────────────┘
      │                            │
      └──── WS server events ──────┘   transcript · processing · answer · error · complete
```

**Frozen:** FastAPI · WebSocket · Sarvam Saaras v3 / Voxtral Mini · Sarvam-105B · Qdrant · React + Vite + TypeScript · 11 locales · no translation layer · contract-first · binary audio frames · normalization at the STT adapter with no Transcript service · `RetrievedContext` as the LLM-independent retrieval boundary.

**Latency:** P100 `total_ms` carries the <200 ms SLO · `retrieval_total_ms` and stage fields provide attribution · STT excluded and reported separately.

**Grounding:** `grounded: false` is a valid Answer · `NO_RELEVANT_CONTEXT` when no evidence · `RAG_ERROR` when a stage malfunctions.

**Deliberately not frozen, resolved by benchmark:** embedding model (0002) · chunking strategy (0003) · reranker keep/drop (0004) · Qdrant collection layout (0005).

---

# Files to change

## Contracts — requires team agreement

| File | Change |
|---|---|
| `00-contracts/answer.schema.json` | Add `retrieval_total_ms` (required), `grounding_ms`, `generation_ttft_ms`; clarify `grounded` and latency descriptions |
| `00-contracts/websocket-server-events.schema.json` | `unevaluatedProperties` fix ×5; remove `GROUNDING_FAILED` |
| `00-contracts/README.md` | Latency section; three grounding outcomes; 9-code error list; local validation; version v1.1 |
| `00-contracts/examples/` | **New** — valid + invalid instances per contract |
| `00-contracts/transcript.schema.json` | *Optional, backend/frontend owners' call* — `stt_latency_ms` |
| `00-contracts/query.schema.json` | **No change** |
| `00-contracts/websocket-client-events.schema.json` | **No change** |

## RAG engine — `03-ai-rag-engine/`

`orchestration/pipeline.py` (segment boundaries, `Query → Answer`) · `orchestration/stages.py` (names matching the `processing` enum) · `orchestration/errors.py` (map to 9 codes) · `guardrails/input_guard.py` · `guardrails/relevance.py` (floor, pre-generation) · `guardrails/grounding.py` (timeout → `grounded: false`) · `retrieval/{vector_store,retriever,reranker}.py` (`RetrievedContext`) · `embeddings/{base,provider}.py` (protocol; winner only) · `generation/{llm,prompts,schemas}.py` · `observability/{metrics,logger}.py` (wall-clock segments; `request_id` logs) · `config/settings.py` · `tests/test_contracts.py` **new** · `__init__.py` across all module dirs **new**

## Evaluation, scripts, docs

`06-evaluation/benchmarks/embeddings.py` **new** · `06-evaluation/metrics/grounding.py` **new** · `06-evaluation/datasets/queries.json` (populate) · `06-evaluation/metrics/{retrieval,latency}.py` · `06-evaluation/benchmarks/{retrieval,latency,end_to_end}.py` · `07-scripts/validate_contracts.py` **new** · `07-scripts/{ingest,build_index,benchmark}.py` · `09-docs/decisions/0002-embedding-model.md` **new, post-benchmark** · `09-docs/evaluation/benchmark-results.md`

## Root

`pyproject.toml` or `requirements.txt` **new** · `.env.example` (populate) · `.gitkeep` in `05-data/*` and `06-evaluation/results/`

## Owned by others — coordinate, do not edit

`01-backend-api/**` · `02-frontend/**` · `04-external-services/**` · `08-infrastructure/**` (Qdrant in compose)

---

# Exact contract changes

## 1. `answer.schema.json` — `$defs.latency`

Replace the `latency` definition's `required` and `properties` with:

```json
"latency": {
  "type": "object",
  "additionalProperties": false,
  "required": ["total_ms", "retrieval_total_ms"],
  "properties": {
    "total_ms": {
      "type": "number",
      "minimum": 0,
      "description": "Wall-clock duration of the full RAG pipeline, from Query received through final serialized output. This is the measurement the <200 ms P100 target applies to. Components are not required to sum to this value; the difference is orchestration overhead. Excludes STT latency."
    },
    "retrieval_total_ms": {
      "type": "number",
      "minimum": 0,
      "description": "Wall-clock duration of the retrieval segment: query embedding, vector search, and reranking. Used for attribution; the project SLO applies to total_ms."
    },
    "embedding_ms": {
      "type": ["number", "null"],
      "minimum": 0,
      "description": "Query embedding only."
    },
    "retrieval_ms": {
      "type": ["number", "null"],
      "minimum": 0,
      "description": "Qdrant vector search only. Does NOT include embedding or reranking."
    },
    "reranking_ms": {
      "type": ["number", "null"],
      "minimum": 0,
      "description": "Reranking only. Null when reranking is disabled."
    },
    "generation_ms": {
      "type": ["number", "null"],
      "minimum": 0,
      "description": "Sarvam-105B generation to the final token. Never time-to-first-token."
    },
    "generation_ttft_ms": {
      "type": ["number", "null"],
      "minimum": 0,
      "description": "Time to first generated token. Populated only when streaming. Must never be reported as generation_ms."
    },
    "grounding_ms": {
      "type": ["number", "null"],
      "minimum": 0,
      "description": "Grounding validation only."
    }
  }
}
```

And on the top-level `grounded` property, replace the description with:

```json
"grounded": {
  "type": "boolean",
  "description": "True when the answer is verified as supported by the returned sources. False when it is NOT verified — either checked and found unsupported, or unverifiable (e.g. the grounding check timed out). False is a valid, successful Answer state, not an error."
}
```

## 2. `websocket-server-events.schema.json` — event composition

Apply to all five events (`transcript`, `processing`, `answer`, `error`, `complete`). Pattern, shown for `transcript`:

```json
"transcript": {
  "type": "object",
  "allOf": [
    { "$ref": "#/$defs/base" },
    {
      "type": "object",
      "properties": {
        "type": { "const": "transcript" },
        "data": {
          "type": "object",
          "additionalProperties": false,
          "required": ["text", "language", "is_final"],
          "properties": {
            "text": { "type": "string" },
            "language": { "$ref": "#/$defs/language" },
            "is_final": { "type": "boolean" }
          }
        }
      },
      "required": ["data"]
    }
  ],
  "unevaluatedProperties": false
}
```

Three changes per event: `additionalProperties: false` **removed** from the inner branch; `"unevaluatedProperties": false` **added** as a sibling of `allOf`; branch `required` reduced to `["data"]` (`base` already requires `type`, `request_id`, `timestamp`). `additionalProperties: false` **stays** on the inner `data` objects, which declare all their own properties and are therefore correct as-is.

The `answer` event keeps `"data": { "$ref": "answer.schema.json" }` unchanged.

Optional tidy, since the eleven-locale enum is currently repeated: add

```json
"language": {
  "type": "string",
  "enum": ["en-IN","hi-IN","bn-IN","ta-IN","te-IN","kn-IN","ml-IN","mr-IN","gu-IN","pa-IN","od-IN"]
}
```

to `$defs` and reference it as above.

## 3. `websocket-server-events.schema.json` — error enum

Remove `GROUNDING_FAILED`, leaving nine codes:

```json
"code": {
  "type": "string",
  "enum": [
    "INVALID_REQUEST",
    "UNSUPPORTED_LANGUAGE",
    "STT_ERROR",
    "STT_TIMEOUT",
    "RAG_ERROR",
    "RAG_TIMEOUT",
    "NO_RELEVANT_CONTEXT",
    "CANCELLED",
    "INTERNAL_ERROR"
  ]
}
```

## 4. Unchanged

`query.schema.json` · `websocket-client-events.schema.json` · `answer.schema.json` apart from `latency` and the `grounded` description · the `"$ref": "answer.schema.json"` reference form.

## 5. Version

Contract version **v1 → v1.1**, recorded in `00-contracts/README.md`.

Strictly, a removed enum member plus a newly-required field is a breaking change. Since **v1 was never implemented** — every code file in the repository is empty — there are no consumers to migrate, and a minor increment with that fact recorded is more honest than a v2 implying a migration that never happened. **The version number is the team's call**; the changes themselves stand either way.

---

# Open items for the team

| # | Item | Owner | Blocks |
|---|---|---|---|
| 1 | Approve the contract changes above | All three | RAG Phase 0 |
| 2 | Contract version: v1.1 or v2 | All three | Nothing — cosmetic |
| 3 | `stt_latency_ms` in `transcript.schema.json` + WS event, for the UI's Latency panel | Backend + Frontend | Frontend Latency component |
| 4 | RAG owns Query/Answer Pydantic models; backend owns WS envelopes | Backend | Duplicate-model risk |
| 5 | Qdrant service in `08-infrastructure/compose/*` | Infrastructure | RAG Phase 6 |
| 6 | Worst-locale Recall floor for the embedding gate | All three | ADR 0002 |
| 7 | Frontend must treat `grounded: false` as success, not error | Frontend | UI correctness |
