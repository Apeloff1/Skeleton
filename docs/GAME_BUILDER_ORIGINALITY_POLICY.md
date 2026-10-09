# No-plagiarism game evolution policy: originality, attribution and lawful inspiration

**Policy:** No deceptive claims of authorship, unattributed third-party expression, or unlicensed incorporation of protected game code, art, audio, characters, story, distinctive level designs or audiovisual presentation. Inspired mechanics and hardware facts remain eligible for *independent* game creation.  
**Review date:** 2026-10-10.  
**Implementation:** `plagiarism_guard.py`, `plagiarism_cli.py`, `legal_paths.py`, `legal_native_export.py`, `rights.py`.  
**Historical scope:** all currently curated systems in `platform_catalog.json`, with no claim that the global archive is complete.

## No universal legal plagiarism percentage exists

A percentage of shared words, lines, screenshots or frames **cannot** decide whether a work infringes copyright. Legal originality, protected expression, substantial similarity and applicable exceptions vary by jurisdiction and individual facts. A project may be unattributed without copyright infringement (ethical plagiarism), and a project with attribution can still infringe if the relevant material was copied without legal permission.

The engineering policy is therefore **stricter than merely passing a similarity threshold**:

1. Preserve authorship/provenance for every asset category and trace the sources of inspiration independently from the game's actual expression.
2. Block knowingly unlicensed protected copying and fabricated authorship claims.
3. Hold for human/legal review when copied expression, questionable musical/artistic similarity, uncertain originality, missing credit, unverified public-domain claims, license restrictions or unverifiable source rights appear.
4. Allow original game-mechanics study without automatically tagging unprotectable rules or hardware facts as plagiarism.
5. Never return a legal clearance certificate just because the automated detector found no matches. A sparse library does not imply a complete search.
6. Do not use euphemisms like "clone," "different enough," "spiritual successor," "fan game," "lost media," "abandonware," "free to play," or "AI-generated" as exemptions from copyright, marks, rights of publicity or protection measures.

### Authoritative cross-reference

**Norway:** [Åndsverkloven § 2](https://lovdata.no/lov/2018-06-15-40/%C2%A72) protects individually original and creative expression. [§ 6](https://lovdata.no/lov/2018-06-15-40/%C2%A76) preserves the possibility of **new independent works inspired by existing works**, while an adaptation does not eliminate rights in the original. Attribution/moral-right concerns and actual authorization must be handled separately. Software interoperability and technological measure questions remain subject to the statute's narrower provisions.

**EU/EEA:** [Directive 2009/24/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024) distinguishes program expression from ideas and interface principles; [CJEU Cofemel, C-683/17](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:62017CJ0683) addresses original expression resulting from free creative choices. A general "20% changed" or "30% matching" rule is **not** an EU originality test.

**United States:** [17 U.S.C. § 102(b)](https://www.govinfo.gov/content/pkg/USCODE-2024-title17/html/USCODE-2024-title17-chap1-sec102.htm) excludes ideas, procedures, methods of operation, concepts and principles from copyright, while protecting eligible original expression. The [U.S. Copyright Office](https://www.copyright.gov/what-is-copyright/) distinguishes independently created original works. [Tetris Holding v Xio Interactive (2012)](https://law.justia.com/cases/federal/district-courts/new-jersey/njdce/3%3A2009cv06115/235418/61/) illustrates why independent source code alone cannot automatically clear copied expressive audiovisual presentation.

**No conclusion here is legal advice or a representation of licensed machine SDKs, game ROMs, protected content or legal distribution rights.**

## Mandatory eight-class declaration

Every candidate game must explicitly disclose whether it uses materials from each area:

| Asset class | Required record | Automated coverage |
| --- | --- | --- |
| Source code and scripts | Author and licence/provenance evidence, source-language samples | Normalized text and token sequence overlap signals |
| Artwork and textures | Artist identity, source, rights and independent visual review | Metadata/provenance gate; **no automatic visual infringement determination** |
| Music and sound | Composition, master recording and source licence separately | Metadata/provenance gate; **no automatic musical infringement determination** |
| Characters | Designs, names, dialogue, traits and source evidence | Text signals, plus mandatory visual review if assets included |
| Story and dialogue | Author, scripts, story outline and reference corpus | Text overlap triage; dramatic structure still requires human comparison |
| Levels and maps | Original geometry, story set-pieces, expressive arrangements | Provenance/level design review, not equivalence of generic tile mechanics |
| Interface appearance | Custom visual expression vs ordinary control principles | Human look-and-feel review for protected arrangements |
| Marketing and branding | Titles, logos, packaging, affiliate claims | Text alerts and trademark/consumer review (separate legal domain) |

Unused categories must be **explicitly** declared `not_used`; silent omissions fail closed. Included material must identify whether it was independently created, licensed, independently verified public-domain, facts/mechanics, uncertain, or unlicensed protected expression. A SHA-256 evidence reference helps bind records but is **not proof** that a declaration is true. Third-party licence scope, real authorship and attribution require independent verification.

Visual/audio similarity **cannot be deemed clear because a textual detector passed**. A reviewer must supply separate evidence for included nontext modalities; lacking it creates a hold.

## Technical triage model and limitations

The tool compares user-supplied *authorized local textual material* against a bounded reference corpus. It tokenizes Unicode text, detects normalized exact copying, longest contiguous phrases, and overlapping six-token windows. Outputs include work IDs, file fingerprints, overlap counts and structured issues. It **does not** include copyrighted source text in a public review receipt.

Text similarity thresholds are merely *flags for investigation*. They do not map to legal thresholds. Generic source conventions, terms required by hardware, genre rules, shared programming-language syntax, historical facts and game rules require idea–expression separation; absence of a machine-readable match cannot conclusively show independent creation.

Reference sources may be licensed or public domain. Attribution and permitted reuse scope are analyzed independently. Public-domain works may not require a copyright licence, but a falsely claimed personal authorship or misleading credit is still disallowed by project policy. Permission to use an asset does not erase credit obligations; giving credit does not replace permission.

## Local, offline operator workflow

Prepare a private `originality_manifest.json` with:
- `schema: "skeleton.originality_input.v1"`, `project_id`, optional current built-world `artifact_sha256`;
- exactly eight `assets` records with `modality`, `disposition`, rights `basis`, provenance/author/license/attribution fields;
- `candidates` and `references` with work IDs, modality, local relative text filenames, and candidate `evidence_sha256` matching the corresponding asset rights reference.

The referenced files must be separately lawfully available for local review, not checked in as copied commercial assets. The scanner is offline: no crawling, ROM dumping, remote search, credential access, model training, or proprietary assets uploaded.

    python -m skeleton.ai.game_builder.plagiarism_cli scan \
      --manifest ./originality_manifest.json \
      --root ./private_review_workspace \
      --receipt ./originality_receipt.json

It rejects absolute paths, directory traversal, symlinked input sources, oversized binary/unknown text, missing disclosures, unknown rights status, and attempts to proclaim globally complete reference coverage. The receipt contains only structured findings and content hashes, not copied narrative or code.

**Release requirements:** The scanner never issues release authorization. A favorable **design** result still requires an independent reviewer to establish authorship, compare high-risk protected expression, verify applicable rights/attribution and SDK/TPM/marketing limitations, and validate the actual native game on its target machine. Human legal decisions must be documented in a separate trust-controlled release process.

### Native export integration

`compile_originality_gated_desktop(world, source, legal_request, originality=report, authorized=True)` is the stricter entrypoint for generating an original C/SDL2 source project. It requires an originality report bound to that **exact game-world digest**, blocks unresolved plagiarism findings and remains non-release-certified. The resulting `legal_review.json` records the scan digest and explicitly reports that it is not a legal originality certificate.

The legacy `compile_rights_aware_desktop` can still produce non-release-certified prototypes without an attached scan, but its receipt explicitly says `plagiarism_screened: false`. It must not be used as a publishing gate.

### Abandoned systems, homebrew and spiritual successors

The archive's old console/computer/arcade profiles are legal and technical *study/reference inputs*. They are **not** libraries of existing commercial game content. The AI can evolve *its own* original game from monochrome to 4K, from sprite to volumetric simulation, and from a 1980s console rule-set to a modern PC build, while maintaining original authorship and documenting influences.

A commercial game having been distributed only on one machine does not, by itself, forbid an independently authored game that uses unprotected mechanics on another machine. It also does not grant authorization to adapt that commercial game's characters, art, dialogue, music, source code or distinctive audiovisual expression. The project must make that separation explicit for **every destination, including discontinued hardware**.

## What remains unsolved

No machine-based classifier can certify worldwide non-plagiarism. Future work includes rightfully acquired reference datasets for sprite/audio/perceptual screening, game-specific semantic level layout comparisons, rights-holder-aware takedown and counterclaim procedures, chain-of-title verification, human reviewer independence and jurisdiction-specific adjudication. Those gaps must not be presented as completed or as a reason to block independently original game *design* forever.
