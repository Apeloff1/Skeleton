# Independently signed game originality and hardware-release review

**Purpose:** Prevent an original homebrew project's old/irrelevant legal and plagiarism checks being silently reused for a modified game, different platform, altered license evidence or new distribution channel.

**System:** `skeleton/ai/game_builder/release_assurance.py`  
**Tests:** `skeleton/testing/test_game_builder_release_assurance.py`  
**Status:** A review-control boundary, **not** a copyright clearance service, automatic release bot, legal certificate or platform-license grant.

## Essential review architecture

The game builder already has machine history, independently authored homebrew world generation, target-specific technical port plans, conservative asset rights assessments, and code/text/image/audio originality triage. None of these outputs is a final permission to publish.

The new gate introduces **10 mandatory independent review domains** across three professional roles:

| Independent role | Required review domains |
| --- | --- |
| Creative and authorship | Authorship and provenance; source-code/text similarity; art/character rights; audio/music rights; story/level rights |
| Qualified rights/legal reviewer | Trademark and trade dress; asset licence chain; national law/hardware technological measures; platform and distribution agreements |
| Technical/hardware reviewer | Native target compilation, packaging, gameplay, input and acceptance evidence |

Each separate domain needs a **detached Ed25519 signature** from a currently trusted reviewer with that domain's authorization. Reviewer key and role permissions are obtained from an **externally provisioned trust registry**. Source generation has no private-key signing function and cannot enroll its own reviewers automatically.

The review candidate includes content-specific bindings to:

- Exact generated world SHA-256 (original homebrew game state);
- Exact native source bundle and compiled native binary digests;
- Legal rights packet and legal assessment digests;
- Originality/anti-plagiarism review digest;
- Actual build and gameplay/replay evidence references;
- Source author IDs, native builders/operators, output machine identity;
- Distribution channel, explicitly enumerated jurisdictions, and needed operator/platform authorization evidence.

The release assessor checks that a signature matches the **current candidate**, the reviewer is in the independent trust registry, the assigned role matches the review domain, the key is not revoked or expired, evidence belongs to the same game, and the person is not the work's author or build operator.

### Tamper and stale-release resistance

Every accepted signature signs a domain-scoped, candidate-bound JSON payload. Changes to native output, source code, rights evidence, cited authorship, declared region, storefront, build/replay evidence or licensing packet change the candidate digest. Old signatures are then **rejected**; a repository branch merge, regenerated game, rereleased binary or renamed ROM cannot inherit approval silently.

Invalid signatures, unknown reviewers, revoked keys, self-reviews, duplicate/conflicting approvals, rejected domains or forged "auto legal clearance" claims are rejected. Missing domains, reviewers or unresolved requests for changes remain pending.

Tests generate private signing keys **in memory exclusively**. No private signing key should be committed to any repository, emitted in build artifacts or shipped in apps. Maintain the independent trusted reviewer registry outside the game development process.

### Correct interpretation of a full-pass gate

A full set of independently verified signatures produces:

`review_receipts_satisfied_publication_pending`

**NOT** "copyright cleared", "original", "independent game legally certified", "publisher-approved", "released" or "console executable verified." All three authorization flags remain `false`, including in the signed-review summary. An actual platform publication still depends on the relevant distributor and legally responsible publisher taking a separate, documented action.

A hash alone does not prove the truth of an ownership declaration. Reviewer signatures prove only that those reviewers signed the specified representations. They do not replace evidence of chain of title, underlying licenses, platform permissions, or a qualified legal assessment in the applicable jurisdictions.

## Homebrew and spiritual successors

This gate applies regardless of whether a game looks like early Pong, a Game Boy puzzle, a Dreamcast exploration game, an Atari arcade title or a modern hybrid. Independent mechanics and hardware interfaces can inspire new games. Protected visual expression, soundtrack, characters, branded presentation and other third-party content cannot be incorporated without an appropriate legal basis.

The game being exclusive to one historic hardware system does **not** mean that underlying gameplay ideas are exclusive to that system. It also does **not** mean copies of that game may be used on every other system.

**Legal references:** [Norwegian Copyright Act](https://lovdata.no/lov/2018-06-15-40), [EU Software Directive 2009/24/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024), [CJEU Cofemel C-683/17](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62017CJ0683), [17 U.S.C. § 102](https://www.govinfo.gov/content/pkg/USCODE-2024-title17/html/USCODE-2024-title17-chap1-sec102.htm), [US Copyright Office — game registration](https://www.copyright.gov/register/tx-games.html). Cite applicable current law and have legal counsel review specific disputes.

## Real author credits and third-party notice artifacts

`asset_credits.compile_game_credits()` now generates deterministic **CREDITS.md**, **THIRD_PARTY_NOTICES.txt**, and **material_inventory.json** from the same project-specific `MaterialRecord` declarations and additional `AttributionEntry` information.

It enforces a one-to-one disclosure for every third-party included component, requires the proposed license name and source rights evidence, flags missing attribution and license text, and prevents unknown or unlicensed protected assets from being buried in a CREDITS file. It includes the author, attributed source title, applicable license declaration, license URL, license-text SHA-256, adapted-use description, destination medium and separate permission evidence. Detected copyleft, share-alike, non-commercial or no-derivative terms require **separate license compatibility/legal review**; no simple pattern match can certify compatibility.

`asset_credits.export_game_credits()` writes the actual files to a new directory without replacing existing notices. Authorship assertions and claimed permission evidence require **independent verification** and cannot grant release authorization. The notes remain part of the game's auditable rights chain and can be attached to the distribution review without copying proprietary art, game executables or ROMs.

## Remediation and operations

1. Generate an original game and its actual target binary from legitimate homebrew source.
2. Run the 8-class originality provenance and media checks. Resolve flagged copying rather than relabeling it "different enough."
3. Independently verify lawful rights material, machine firmware/SDK access, third-party licences, country limitations and contractual channel terms.
4. Enroll qualified reviewers via separately administered key-management policies and request signed evidence for each mandatory review domain.
5. Run `evaluate_independent_review(candidate, legal, originality, trust_registry=..., attestations=..., evaluation_utc=...)`.
6. Do **not** publish solely because the gate passes. The responsible publisher retains final authority and can require further compliance, actual console certification and legal opinions. Revoked, expired or modified evidence requires fresh independent decisions.

### Current limitations

The reviewed source artifacts are only as trustworthy as the underlying provenance and outside reviewers. Automatic art/audio fingerprinting is heuristic; no similarity percentage is a legal standard. No global historical game archive or legal rightsholder database can be declared exhaustive; isolated platforms, regional clones, distributor changes, and national limits need continued investigation. This module intentionally cannot issue legal release authorization.

Release attestations currently use explicit platform and jurisdiction identifiers as assertions tied to signatures; verification of actual build log signatures, transparency-log inclusion, external publisher identity and dynamic platform agreements requires separate independently managed infrastructure.
