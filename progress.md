# Research progress

- 2026-10-28: User requested GitHub ecosystem maturity and high-star references for all four topics, with three days available.
- Read planning-with-files skill; created research files in empty workspace.
- Delegated topic 1, topic 2, and topic 4 to independent research agents; primary agent covers topic 3 and synthesis.
- First primary-source search found RAGFlow, FastGPT, and Onyx; beginning repository and maintenance checks.
- Verified current topic 3 repository/API snapshots and releases. Identified direct shell TLS limitation and used browser sources.
- Collected independent source-based reports for topics 1, 2, and 4, including selected source-code checks and archival status.
- Recorded approximate stars, maintenance evidence, application/framework/example distinctions, and acceptance gaps for all four topics.
- Research complete. Preparing Chinese comparison; no repositories installed or executed.
- User excluded topic 3 and focused exploration on topic 4. Rechecked source and independently reviewed minimal design/acceptance mapping. No implementation started.
- 2026-10-30: User authorized full implementation of accepted Python/LangGraph/16-skills/three-review-gates CLI plan. Confirmed workspace has only research files, Python 3.12.9 and Git; LangGraph and pytest not yet installed.
- Parallel implementation established contracts for tools, skills/data, and model/prompts. Core graph and SQLite runtime written. Initial pip build-isolation install stalled; explicit PyPI dependency install progressed but timed out fetching a wheel, retrying with a 60-second read timeout and workspace cache.

- Core implementation complete: LangGraph decision loop, 16 skill packages, SQLite checkpoints, three version-bound human review gates, source/duration checks, explicit mock, CLI and artifact export.
- Offline suite executed 13 cases; flow evidence retained separately from live evidence. Full tests after prompt integration: 90 passed in 11.32 seconds; JUnit saved in examples/test-results.xml.
- First live business run exposed the model service's old 4096-token context ceiling. Preserved its failed record in examples/experiments/context-4k. User restarted service with 32768 tokens; /models and a real chat request verified the change. Continuing actual model acceptance, without mock fallback.

- Native business evaluation revealed malformed long tool responses, skill IDs misused as tool names, repeated checking without revisions, and unnecessary clarifications. These records are preserved in examples/experiments/native-business. None are promoted to success.
- Fixed context projection to retain initial drafts even during direction planning, all loaded method instructions once, full issue locations and recent actual actions. Fixed skill-to-artifact event indexing and graph recursion limits for non-default budgets.
- Added explicit JSON action protocol without automatic fallback. First JSON-object test returned wrong top-level keys; preserved examples/live-json/normal. A strict JSON-schema action union was then verified against the actual endpoint (HTTP 200), pending full acceptance.

- Final verification: 220 executable tests passed in 29.05 seconds; final explicit Mock suite 14/14 passed. pip check found no broken requirements. These are engineering/flow results, not proof of live model quality.
- Final live evidence keeps 14 latest case records across iterative batches: no-materials, conflict, and budget-limit expectations passed; 11 cases did not meet their full acceptance expectations. No live run falsely marked a rejected script completed. Two final independent-process cases (normal/tool_failure) used identical import-time source fingerprints and still ended incomplete.
- Confirmed actual model-driven branches: conflicting sources -> supplemental search -> clarification; injected tool error -> explicitly simulated human reminder -> changed search succeeds -> later duration failure. Detailed seq references are in docs/03-evaluation.md.
- Added bounded model patch operations, current-state action preconditions, preserved human clarification context, strict JSON Schema protocol, and truthful code-version snapshots. 16 skills are implemented; 16 loaded and 7 model-declared associations do not prove effective application.
- User was asked asynchronously whether another instruction-model endpoint is available; no answer was received during this implementation. Continued with the supplied model and retained failures rather than relaxing checks.
- Local Git repository initialized. Preparing a reviewable source archive and local commit; GitHub remote is not supplied, full live acceptance remains outstanding.

- Local source archive extracted into an isolated workspace subdirectory; verified imports came from the extracted source and all three Mock review gates completed. No .env, runtime DB, cache or virtualenv in the archive. Code fingerprints retained in examples/package-check.json. Local Git commit and archive are ready; remaining live acceptance and remote publication are explicitly pending.

- DeepSeek integration started 2026-10-30 23:53 Asia/Shanghai. User provided an ignored local key and authorized system testing with deepseek-flash, 16k application context budget and 4k output reserve. Existing Qwen traces remain baseline evidence. Official API defaults to thinking enabled; adapter must explicitly disable it because this implementation deliberately does not store/replay private reasoning. The previously written LLM_CONTEXT_WINDOW value was not enforced by prior code; implementing actual pre-request checking now.

- 2026-10-31T00:31+08:00: DeepSeek integration phase verified. Native non-thinking API connected after sandbox approval retry. All 14 live cases attempted: raw 8 automated expectations met, 6 interrupted by provider HTTP 402 Insufficient Balance. No further API calls after diagnosis; user asked asynchronously whether to restore balance.
- AI-assisted artifact review found unsupported UI/operations and compound citation gaps in normal, missing_info, tool_failure and duration_revision. Original records retained; manual_audit.json stores findings and hashes. Added evidence_required_terms guards, stronger full-script/per-claim prompts, semantic metadata correction and semantic-error evidence. Offline recheck blocks the four historical scripts; corrected live behavior is not yet verified.
- Final corrected source: 282 tests passed in 23.66s, Mock 14/14 passed, extracted archive completed all review gates and local tokenizer probe. Secret scan and documentation links passed. Preparing updated local commit and archive; GitHub remote remains absent. Phase began 23:53 on Oct 30; this timestamp records actual elapsed wall time, not candidate manual effort.
