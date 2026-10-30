# GitHub research plan

Goal: Compare mature open-source references for the four campus Agent assignments, including verified popularity, maintenance, functional fit, and remaining work for a three-day submission.

## Phases
- [complete] Establish scope and delegate independent research for topics 1, 2, and 4.
- [complete] Inspect primary GitHub sources and release activity; research topic 3.
- [complete] Cross-check reported stars and distinguish applications, frameworks, and examples.
- [complete] Prepare a Chinese comparison with direct sources and practical implications.
- [complete] Respect exclusion of topic 3; explore a concrete topic 4 concept and acceptance boundaries without implementing it.

## Historical research-stage constraints (superseded by implementation authorization below)
- At the research stage only: do not implement an assignment or install repository code.
- Stars are popularity signals, not proof of reliability or acceptance coverage.
- User-facing research date: 2026-10-28, Asia/Shanghai.
- Identify cached page figures as approximate; do not claim live counts without evidence.

## Errors
- Workspace listing and file search returned no existing project files (expected empty workspace).
- Direct PowerShell GitHub API request failed TLS authentication; switched to browser-accessible GitHub API and repository pages.
- Browser API endpoint for Onyx was inaccessible; use its official organization/repository pages instead.
- Implementation dependency install: default build isolation stalled; explicit PyPI install timed out on a wheel; retry returned an empty Typer wheel rejected by SHA-256 validation. Kept hash checks enabled, switched to the Tsinghua HTTPS mirror and pinned Typer/pytest stable versions.

## Implementation: 2026-10-30
User authorized implementing topic 4 according to the accepted plan. Python CLI, LangGraph, 16 progressively loaded business skills, three human review gates, synthetic product/brand JSON, configurable compatible API and explicit offline Mock. Live endpoint preflight succeeded at http://127.0.0.1:8012/v1 using qwen25-14b-pbn-answer, including sequential tool-feedback adjustment.

- [complete] Establish package/contracts, development environment, synthetic data and skills.
- [complete] Implement model adapter, graph, durable review/resume, checks, CLI and exports.
- [complete] Run deterministic tests and real-model acceptance paths; fix engineering defects and preserve unresolved model failures.
- [complete] Generate evidence and honest skill coverage; finish requirements/design/evaluation/AI-use/retrospective documentation.
- [complete] Verify local deliverable, create local Git commit and source archive; extracted archive imports and completes the three offline review gates.
- [pending] Meet the full live business acceptance criteria using an adequate model configuration, then publish to a supplied GitHub remote.

Constraints: no real video generation; no false claims of live model/skill coverage or human approval; simulated reviewer decisions in evaluation must be labeled. Preserve local API credentials outside tracked evidence. Remote GitHub destination has not been supplied.

## DeepSeek integration: 2026-10-30
User supplied a private API key and authorized DeepSeek Flash as the primary runtime model, with a 16,384-token application budget and 4,096-token output reservation. Topic 4 remains the selected assignment.
- [complete] Explicit non-thinking native tool protocol; enforce and disclose local context estimation.
- [complete] API connectivity and normal / duration-revision flow smoke; later content audit requires revalidation.
- [complete] Attempt all 14 cases, preserve Qwen baseline, review traces and fix observed UI/feature grounding defects. Raw 8 automated passes; 6 HTTP 402 failures; 4 completed scripts require content revalidation.
- [complete] Update evidence, documentation, tests and archive smoke: 321 tests, 14 Mock cases passed; all four live batches and latest failures retained.
- [resolved for first interruption] User restored API balance and further live batches ran. The second HTTP 402 later stopped paid calls; new verification needs available quota and an explicit whole-experiment budget. Remote publication still needs a supplied destination.

- [complete] User restored balance; executed further real comparisons and targeted skill checks, then stopped paid calls at the second HTTP 402.
- [pending] Reliable long revision convergence, final live revalidation within a total experiment budget, and remote publication. Latest records are not all passing.
