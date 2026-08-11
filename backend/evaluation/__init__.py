"""Offline trajectory capture harness.

Phase 0 scope (per plan revision 2026-04-30):
- bootstrap a consent-filtered query set from MongoDB conversations
- replay each query through the LangChain graph stack
- persist the trajectory (spans + response + cost) as JSONL

Intentionally NOT in scope: LLM judge, rubric scoring, markdown reports,
comparison subcommand. Those defer to Phase 1+ when we have two backends.
"""
