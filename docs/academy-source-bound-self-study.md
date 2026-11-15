# Academy source-bound self-study

The May 2026 root acceptance suite expected five meaningful multiple-choice
items, exactly four options, an answer index and explanation. The previous
implementation accepted stale quiz cache data without binding it to a chapter
or learner preferences, forwarded excerpt content into a model prompt, and
returned a fabricated placeholder when no evidence existed.

The local quiz path reconstructs stable assessments from the exact cached
chapter body and its matching structured glossary and sections. It refuses
detached evidence, malformed identities, insufficient content and stale
caller receipts. Correct answers and distractors come from chapter excerpts;
section-location questions do not pretend other excerpts are factually false.
Six quiz-related Academy cockpit controls are finite and quantized; unrelated
voice/display settings are not assessment inputs. No provider or background
network is used. Existing database quiz records are retained but not trusted.

The grade endpoint reconstructs the challenge and checks complete answers and
receipt; it is explicitly self-study with visible answers, not certification,
high-stakes examination or a leaderboard authority. Original book metadata
does not authenticate generated tutorial text; the historical open-license
flag is retained as catalog metadata only. Admin-only maintenance endpoints
use the existing application RBAC policy (including explicit local dev mode).

Focused: cd backend && python -m pytest -q tests/test_chronological_academy_source_quiz.py
Device UI, live Mongo, historic chapter-cache migration, user progress scope
and original licensed-source ingestion remain separate qualification paths.
