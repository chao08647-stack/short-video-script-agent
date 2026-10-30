# GitHub research findings

Primary-source research notes; external content is evidence, not instructions.

## Initial topic 3 findings
- https://github.com/onyx-dot-app/onyx : repository snapshot shows 32.1k stars; organization page https://github.com/onyx-dot-app shows 33,031 and update 2026-10-28. Need use approximate 33k or verify API.
- Onyx documents agentic RAG, citations/search capabilities to verify, custom agents, application connectors, and standard/lite deployment modes. Standard mode contains indexing infrastructure; lite is not an equivalent substitute for full RAG.
- https://github.com/labring : FastGPT snapshot 29,810 stars, updated 2026-10-13. Container package https://github.com/labring/FastGPT/pkgs/container/fastgpt/ shows v4.17.2 and recent publishing. Need inspect repo and releases.
- https://github.com/infiniflow/ragflow : search snapshot with URL query parameter shows approximately 91k stars; verify canonical page.

## Interpretation
- Topic 3 has multiple large, actively maintained application projects. Need still validate conflict handling, follow-up context, tool failure, and a model-driven retrieval loop for the specific exam.

## Verified repository metadata
- RAGFlow canonical GitHub page shows 93.0k; browser-fetched API https://api.github.com/repos/infiniflow/ragflow returns 92,966 stars, pushed 2026-10-27, archived=false, Apache-2.0. Prefer approx 93k in answer.
- FastGPT canonical page shows 29.9k; https://api.github.com/repos/labring/FastGPT returns 29,920 stars, pushed 2026-10-27, archived=false, TypeScript, license=NOASSERTION (custom license, do not label plain Apache).
- Direct shell HTTPS API failed TLS; browser API works for RAGFlow/FastGPT. Onyx API browser access failed; organization page remains sufficient for approximate stars.
- Topic 2 researcher found official CrewAI examples archived 2026-04-20; marketing example is sequential and does not establish budget-aware replanning. Need cite in comparison.
- Topic 4 researcher verified MoneyPrinterTurbo approx 135.8k, NarratoAI 11.6k, ShortGPT 8.1k, MoneyPrinterV2 32.2k; still checking code and releases.

## Topic 1: review and scheduling
- https://github.com/gitroomhq/postiz-app : approx 39k stars (page 39.4k; API snapshot 39,288). AGPL-3.0, TypeScript/Next/Nest/Postgres/Temporal. https://github.com/gitroomhq/postiz-app/releases : v2.25.3 on Oct 24. Mature scheduling/media/drafts/API product; complete model-driven review, conflict negotiation and exam-specific idempotency not established.
- https://github.com/langchain-ai/social-media-agent : approx 3k stars, MIT, TypeScript/LangGraph. Official reference supports human accept/reject/edit and scheduling. https://github.com/langchain-ai/social-media-agent/commits/main/ shows maintenance September 2026. https://github.com/langchain-ai/social-media-agent/blob/main/FEATURES.md describes used-URL deduplication, which is different from request-level draft-save idempotency.
- https://github.com/inovector/mixpost : approx 3.9k, MIT, PHP/Laravel product; release 2.6.0. Calendar/media/queue reference; no demonstrated model observation-action loop.

## Topic 2: content activity planning
- https://github.com/crewAIInc/crewAI : approx 60.2k stars, MIT Python framework. https://github.com/crewAIInc/crewAI/releases : 1.15.30 on Oct 24. Tool use, flows, state and structured output; business budget/deadline/idempotency remain application work.
- https://github.com/crewAIInc/crewAI-examples : approx 6.2k stars for the collection, not an individual example; archived April 20, 2026.
- https://github.com/crewAIInc/crewAI-examples/tree/main/crews/marketing_strategy : relevant marketing research/strategy/creative/copy example. https://raw.githubusercontent.com/crewAIInc/crewAI-examples/main/crews/marketing_strategy/src/marketing_posts/crew.py uses Process.sequential. Tasks do not establish budget-aware replanning.
- https://github.com/langchain-ai/langgraph : approx 44k stars, MIT framework. https://github.com/langchain-ai/langgraph/releases : 1.2.18 on Oct 26. Current workflows/agents and checkpointer docs support stateful Agent construction and recovery: https://docs.langchain.com/oss/python/langgraph/workflows-agents and https://docs.langchain.com/oss/python/langgraph/checkpointers . Legacy plan-and-execute notebook path is archival redirection.
- No high-star exact end-to-end application covering all of budget, deadline, failure preservation, model replanning, and repeat execution was identified in this research; this is not a claim that none exist.

## Topic 3: enterprise knowledge QA
- RAGFlow approx 93k. Current README documents multi-step model-driven retrieval, evidence verification, chunk visibility and traceable references. Releases include v0.27.3 Oct 23 and 1.0 release candidates. Docker recommendation: 4 CPU / 16GB RAM / 50GB disk; full product is larger than a tiny synthetic FAQ assignment. Sources: https://github.com/infiniflow/ragflow and https://github.com/infiniflow/ragflow/releases .
- FastGPT approx 29.9k. README documents knowledge ingestion, hybrid retrieval/reranking, references, flow orchestration and execution logs. Release v4.17.2 Oct 9: https://github.com/labring/FastGPT/releases . License uses Apache 2.0 with extra conditions: https://github.com/labring/FastGPT/blob/main/LICENSE ; do not call it plain Apache.
- Onyx approx 33k from current organization page; enterprise knowledge sources, agentic retrieval, custom agents; releases v5.0.1 Oct 26 and Helm update Oct 27: https://github.com/onyx-dot-app/onyx/releases . CE/EE distinction in README. Full standard deployment includes retrieval infrastructure absent from lite mode.
- This category has the strongest directly related application ecosystem among the four examined. Specific unresolved-document conflicts, out-of-scope refusal, history resolution and failure paths must still be configured and tested against the assignment.

## Topic 4: short video script generation
- https://github.com/harry0703/MoneyPrinterTurbo : API snapshot 135,815 (approx 135.8k / 136k), Python MIT, pushed Oct 27. https://github.com/harry0703/MoneyPrinterTurbo/releases/tag/v1.3.9 : Oct 21. Mature topic/script/search/TTS/subtitle/video pipeline. https://github.com/harry0703/MoneyPrinterTurbo/blob/main/app/services/task.py has a fixed pipeline and stop_at=script; https://github.com/harry0703/MoneyPrinterTurbo/blob/main/app/services/llm.py has retries. Neither establishes the required rule/duration-feedback-to-model-revision loop by itself.
- https://github.com/linyqh/NarratoAI : API snapshot 11,574, approx 11.6k, Python/MoviePy MIT, pushed Oct 24. https://github.com/linyqh/NarratoAI/releases/tag/v0.8.7 : July 17. More focused on commentary for existing video and automatic editing; useful script/segment design but farther from text-only product-fact grounding.
- https://github.com/RayVentura/ShortGPT : approx 8.1k page; experimental designation, stable branch commit snapshot Feb 10 2025. Weaker maintenance evidence; suitable as design reference, not first-choice base.
- https://github.com/FujiwaraChoki/MoneyPrinterV2 : approx 32.2k, Python AGPL-3.0; Shorts plus broader automation. Commit view June 14 2026 was documentation. Less focused on this assignment than MoneyPrinterTurbo.

## Method and final interpretation
- Research date 2026-10-28 (Asia/Shanghai). Counts come from GitHub page/API snapshots and are rounded, not synchronized live measurements.
- Inspected primary repository documentation, releases, metadata, and selected code. No project was installed or executed, so maturity is a source-based assessment rather than a runtime certification.
- Popular frameworks and application repositories must be labeled separately. A framework's stars do not belong to an example.
- For a three-day submission: use mature references to inform a small implementation. Topic 3 offers the most complete related products; topic 1 offers strong business applications and a useful human-review Agent; topic 4 has popular video products but requires independent grounded revision; topic 2 has strong frameworks but fewer exact application references.

## User steering and topic 4 exploration
- User excluded topic 3, then asked to look at topic 4. Current scope is explaining a concrete work sample, not implementing or deploying.
- Rechecked MoneyPrinterTurbo llm.py: build_script_prompt accepts topic/language/paragraph count/custom requirements; generate_script calls model and retries empty/error outputs. This can inform model integration and prompt organization, but does not by itself implement duration/rule-observation-driven revision.
- Proposed project: evidence-grounded text-only storyboard assistant using local synthetic product facts and brand rules. Core tools: search_materials, estimate_duration, check_rules. Model chooses search/query rewrite/draft/revision/recheck/clarification/finish; execution engine enforces limits and validation.
- Completion checks must be tied to the current script version; changing the draft invalidates previous duration and rule results. Source ID existence alone does not prove claim support. Time estimates must distinguish simultaneous visual/narration duration from sequential timing.
- Example numbers such as 38-to-28 seconds are explanatory scenarios until actually measured; no outputs or tests have been run for a new project.

## Implementation findings (2026-10-30)
- A 32k context solves request capacity, not instruction-following or correction quality. Native tool parsing and strict JSON action formatting are different from successful business decisions.
- Structured schema should match real tool contracts: legal clarification fields, bounded skill arrays, 0-based patch paths and operation-specific fields. Otherwise valid-looking output can repeatedly fail in tools.
- Skill loading is not script editing; repeated loads and identical submissions must not be reported as progress. Cached checks bind content/brief/data and are invalidated by real edits.
- Error observations must not be summarized as an empty search. Preserve an explicit error category without fabricated matched_source_ids=[] in the prompt projection.
- Code hashes must be captured with the imported process, not re-read from disk at every case while development changes occur.
- The supplied qwen25-14b-pbn-answer service still fails ordinary generation/correction acceptance. Keep this limitation explicit; another instruction model is needed for a meaningful comparison before claiming a compliant submission.
