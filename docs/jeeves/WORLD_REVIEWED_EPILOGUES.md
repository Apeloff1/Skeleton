# Reviewed original ending epilogues

This vertical turns original author prompts and ending-specific prose into
source-leased, replay-verified player closure. It does not impersonate an LLM
generation. The operator authors the exact text; Jeeves provides a typed
read-only proposal preview, and the CLI owns persistence and approval.

## Flow

1. Create an original canonical world and a player slot.
2. Author JSON with `prompt` and `entries`: one sorted
   `{scene,title,text}` object for every canonical ending scene.
3. Run `world-epilogues --store STORE propose --world-id ID --file INPUT.json`.
   Review and save the returned `proposal`.
4. Run `world-epilogues --store STORE publish --world-id ID --file
   PROPOSAL.json --create --expected-digest unused`.
5. Explicitly approve the source with `approve --expected-digest DIGEST
   --note "reviewed original text"`.
6. Finish a native `world-session` player trace. `player --slot SLOT`
   replays the full session and refuses an unearned ending.
7. Run `compile --slot SLOT --expected-digest EPILOGUE_DIGEST
   --expected-session-digest SESSION_DIGEST`, then `verify`.

The output is a no-script, CSP-constrained offline HTML5 epilogue with the
actual earned ending and recorded choices, plus a source-bound manifest
receipt. All source and session reads are descriptor-anchored and bounded.
Source updates require an exact digest and invalidate prior approval;
compilation requires current approved source and current player digest.
A failed, skipped or pending CI gate is never release certification.

## Offline visual authoring

Before approval, run `world-epilogues --store STORE editor --world-id ID
--expected-digest SOURCE_DIGEST`. The generated private HTML page has a
hash-constrained script, no network access and original ending-specific
prose fields. Its JSON export is explicitly **unapproved**. Import the
export through the normal source-leased `publish` action, re-review the
content and explicitly `approve` again. The editor cannot grant endings
or bypass source, session, and approval validation.
