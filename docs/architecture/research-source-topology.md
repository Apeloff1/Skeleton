# Research Source Topology and Ingestion Policy

Status: canonical source-discovery and evidence-ingestion map
Updated: 2026-09-21
Track: AD

## 0. Principle

Research discovery must not collapse onto a single archive, search engine, lab, or citation graph.

Different sources answer different questions:

- **Does the work exist?**
- **What version is current?**
- **Was it accepted, rejected, withdrawn, corrected, or retracted?**
- **What did the authors actually claim?**
- **Is code/data available?**
- **Was it independently reproduced?**
- **What failed in practice?**
- **What standard, law, or protocol constrains implementation?**

No source family answers all of them.

## 1. Source-family registry — RS001..RS055

| ID | Class | Source family | Primary use | Skeleton caution |
| --- | --- | --- | --- | --- |
| RS001 | preprints | arXiv | versioned preprints and metadata | high discovery value; peer-review status separate |
| RS002 | reviews/submissions | OpenReview | forum, revisions, reviews, decisions, withdrawals | decision/status must be preserved exactly |
| RS003 | bibliographic metadata | Crossref | DOI metadata and publication identity | metadata source, not scientific truth |
| RS004 | open scholarly graph | OpenAlex | works/authors/institutions/citations/concepts | use for discovery/lineage; verify primary source |
| RS005 | computer-science bibliography | DBLP | CS publication metadata | strong bibliographic disambiguation; not claim authority |
| RS006 | scholarly graph | Semantic Scholar | paper graph, references, citations, metadata | secondary discovery surface; primary-source follow-up required |
| RS007 | NLP proceedings | ACL Anthology | ACL-family proceedings and PDFs | preferred primary venue source for NLP acceptance |
| RS008 | ML proceedings | PMLR | ICML/AISTATS/CoRL and related proceedings | primary published proceedings where applicable |
| RS009 | ML proceedings | NeurIPS proceedings | accepted NeurIPS papers/proceedings | venue identity and official paper |
| RS010 | vision proceedings | CVF Open Access | CVPR/ICCV/WACV papers | primary public proceedings for covered venues |
| RS011 | computing library | ACM Digital Library | peer-reviewed CS proceedings/journals | paywall/access varies; metadata still useful |
| RS012 | engineering library | IEEE Xplore | IEEE journals/conferences/standards papers | metadata/status strong; access varies |
| RS013 | security proceedings | USENIX | systems/security papers and artifacts | high-value systems/security primary source |
| RS014 | cryptography archive | IACR ePrint | cryptography preprints | preprint status separate from CRYPTO/EUROCRYPT publication |
| RS015 | medical bibliography | PubMed | biomedical publication metadata | domain-specific evidence; study design/clinical authority separate |
| RS016 | biomedical fulltext | Europe PMC | biomedical metadata/full text where available | supports citation/full-text retrieval |
| RS017 | biology preprints | bioRxiv | life-science preprints | preprint, not peer-reviewed by default |
| RS018 | medical preprints | medRxiv | health-science preprints | high-risk domain: preprint warning mandatory |
| RS019 | general repositories | Zenodo | datasets/software/papers with DOI-style records | artifact provenance useful; review status varies |
| RS020 | open repository | HAL | multidisciplinary papers/preprints | repository status preserved |
| RS021 | economics/social science | SSRN | working papers/preprints | working-paper status explicit |
| RS022 | physics/astronomy | NASA ADS | astronomy/physics bibliographic graph | domain discovery and citation lineage |
| RS023 | chemistry | ChemRxiv | chemistry preprints | preprint status explicit |
| RS024 | patents | Google Patents / Espacenet / USPTO/EPO records | prior-art and engineering-disclosure research | legal status and scientific evidence are separate |
| RS025 | standards | NIST publications | standards, evaluations, security/measurement guidance | normative/technical role recorded |
| RS026 | standards | IETF RFCs | internet protocol standards and practices | status category—standard/proposed/informational—preserved |
| RS027 | standards | W3C Recommendations | web standards | normative status/version preserved |
| RS028 | standards | ISO/IEC metadata | formal standards | licensed text may limit ingestion; metadata/version still tracked |
| RS029 | software | GitHub repositories/releases | reference implementations, issues, commits, releases | bind exact commit/release; repo popularity not evidence |
| RS030 | software | GitLab/other source forges | code/artifacts/issues | bind exact revision and provenance |
| RS031 | model artifacts | Hugging Face Hub | model cards, weights, datasets, spaces | bind revision/commit; card claims remain first-party |
| RS032 | datasets | official benchmark repositories | task data, scoring scripts, version history | benchmark custody/version essential |
| RS033 | leaderboards | official challenge leaderboards | current scores/submissions | leaderboard rank is discovery, not sufficient promotion evidence |
| RS034 | reproducibility | Papers with Code style indexes / artifact badges | implementation/discovery links | verify maintained canonical code; indexes can be stale |
| RS035 | journals | JMLR | ML journal papers | peer-reviewed primary source |
| RS036 | journals | Nature/Science family | cross-disciplinary peer-reviewed research | press summary never substitutes for paper/methods |
| RS037 | journals | SpringerLink | journals/books/proceedings | publication metadata and primary papers |
| RS038 | journals | ScienceDirect/Elsevier | journals/books | publication metadata and primary papers |
| RS039 | math | zbMATH / MathSciNet metadata | mathematical bibliographic validation | secondary bibliographic source |
| RS040 | formal-method artifacts | Archive of Formal Proofs / theorem-prover libraries | machine-checked proof artifacts | proof environment/version is part of identity |
| RS041 | vulnerability | NVD/CVE records | security vulnerability identifiers/severity metadata | severity/status can change; vendor advisories cross-check |
| RS042 | security advisories | vendor security advisories | first-party vulnerability/fix details | cross-check independent sources when consequential |
| RS043 | incident evidence | postmortems and reliability incident reports | real failure modes and recovery lessons | first-party operational evidence; causal claims scoped |
| RS044 | regulation/policy | official government/regulator publications | laws/rules/guidance affecting system constraints | jurisdiction/date/version mandatory |
| RS045 | technical blogs | official research lab engineering/research pages | deployment-scale evidence and unpublished methods | first-party evidence class; not independent consensus |
| RS046 | independent critique | technical replications/critiques | negative evidence, reproductions, corrections | methods quality assessed; criticism is not true by default |
| RS047 | theses | institutional dissertation repositories | deep methods/history often omitted from papers | degree/institution/version metadata preserved |
| RS048 | conference media | recorded talks/posters/slides | clarifications and implementation detail | secondary to paper/artifact for claim identity |
| RS049 | discussion | author issue trackers/discussion forums | implementation ambiguities and failure reports | anecdotal/emerging until reproduced |
| RS050 | web archive | Internet Archive / archived project pages | historical artifact recovery and version context | archive timestamp/provenance mandatory |
| RS051 | books/monographs | publisher/ISBN records | foundational syntheses and mature theory | edition/version matters |
| RS052 | measurement data | MLPerf and similar standardized benchmarks | hardware/system performance comparisons | exact benchmark version/config/hardware required |
| RS053 | energy/hardware | vendor architecture manuals | ISA/kernel/device capabilities | first-party hardware spec; measured performance separate |
| RS054 | research data | institutional/open data repositories | raw experimental datasets | license, schema, provenance, update version required |
| RS055 | retractions/corrections | Crossmark/Retraction Watch-style discovery plus publisher notices | corrections/retractions | publisher/venue correction is authoritative status source when available |

## 2. Source resolution order

When status matters, prefer:

1. official venue/publisher decision record;
2. primary preprint/version record;
3. author/institution artifact record;
4. trusted bibliographic metadata;
5. secondary scholarly graph/search;
6. discussion/social summaries only as discovery leads.

When implementation details matter, prefer:

1. exact tagged/released code;
2. commit used by the paper if known;
3. artifact-evaluation package;
4. author implementation;
5. independent reproduction;
6. third-party rewrite.

When a result is contested, collect **both**:
- the strongest supporting source;
- the strongest methodologically relevant counterevidence.

## 3. Source adapter contract

~~~text
ResearchSourceAdapter
  source_family_id
  adapter_version
  query_capabilities
  identifier_types[]
  fetch_metadata()
  fetch_versions()
  fetch_status()
  fetch_artifacts()
  fetch_citations()
  fetch_corrections()
  rate_limit_policy
  auth_policy
  terms_or_license_notes
  parser_version
~~~

Adapters retrieve evidence. They do not decide truth.

## 4. Identity resolution

One work can appear as:
- arXiv preprint;
- OpenReview submission;
- accepted proceedings paper;
- publisher DOI;
- GitHub repository;
- model/dataset release.

Create a WorkIdentity graph:

~~~text
work_id
  -> preprint versions[]
  -> submissions[]
  -> accepted publications[]
  -> corrections/retractions[]
  -> code artifacts[]
  -> data artifacts[]
  -> model artifacts[]
  -> replications[]
~~~

Do not duplicate these into independent "papers" merely because URLs differ.

## 5. Version policy

Record:
- first-seen timestamp;
- exact version;
- latest observed version;
- content digest where permitted;
- status at decision time;
- later status transitions.

A revised paper can change:
- result;
- method;
- limitations;
- author list;
- venue status.

Architecture decisions remain linked to the exact version they used.

## 6. Citation-graph caution

Citation count is not evidence independence.

Correlations include:
- one lab citing itself;
- derivative papers using the same code/data;
- benchmark monoculture;
- one provider underlying many experiments;
- survey papers repeating one original result.

Use citation graphs for discovery and lineage, never as a truth score.

## 7. Artifact triangulation

A high-impact result should ideally connect:

~~~text
paper
 + code
 + config
 + data
 + model/checkpoint
 + evaluation script
 + environment
 + independent reproduction
~~~

Missing components become explicit reproducibility debt.

## 8. Negative-evidence discovery

Search intentionally for:
- "fails to";
- "negative result";
- "reproduction";
- "replication";
- "limitations";
- "critique";
- "revisiting";
- "does not";
- "underperform";
- "instability";
- "collapse";
- "attack";
- "counterexample";
- "withdrawn";
- "retracted";
- "erratum".

Research search is biased if it only looks for papers claiming improvement.

## 9. Non-paper evidence

System architecture must ingest evidence from:
- incident postmortems;
- standards;
- security advisories;
- hardware manuals;
- benchmark issue trackers;
- code commits;
- bug reports;
- reproducibility artifacts;
- formal proofs;
- legal/regulatory texts where applicable.

A systems failure observed in production can outweigh a clean paper benchmark for that operational condition.

## 10. Archive failure and disappearance

Sources can:
- disappear;
- change URLs;
- remove artifacts;
- rewrite project pages;
- lose dependencies.

Preserve durable identifiers and metadata. Where licensing permits, store checksums and locally durable metadata/artifact references.

Never assume a live URL is permanent provenance.

## 11. Research-source security

Treat fetched PDFs, archives, repositories, notebooks, model files, and webpages as untrusted.

Before execution or privileged parsing:
- size limits;
- archive/decompression limits;
- safe parsing;
- malware scan;
- secret scan;
- dependency isolation;
- sandbox execution;
- no ambient credentials.

Research ingestion inherits Track AB security.

## 12. Source freshness jobs

A refresh worker may check:
- new versions;
- venue decisions;
- corrections/retractions;
- repository releases;
- benchmark revisions;
- model/data releases.

Its output is a change receipt and review task.

It may **not** automatically rewrite current architecture conclusions.

## 13. Coverage requirements

For a major research question, avoid one-source-family monoculture when alternatives exist.

Preferred triangulation:
- primary research paper/preprint;
- artifact/code;
- independent or negative evidence;
- systems/standard evidence where relevant.

For high-impact safety/system claims, first-party evidence is useful but cross-lab or local replication should be sought.

## 14. Source-quality anti-patterns

Reject:
- search-result snippet as evidence;
- press article as substitute for methods;
- copied blog benchmark without config;
- leaderboard rank without task/version;
- GitHub stars as scientific maturity;
- citation count as replication;
- "accepted" inferred from conference year in title;
- arXiv submission interpreted as peer review;
- vendor performance claim interpreted as independent benchmark;
- withdrawn work silently deleted from history.

## 15. Planning checkpoint

~~~text
checkpoint_id: PLAN-20260921-RESEARCH-SOURCE-TOPOLOGY
created_at: 2026-09-21
source_families: RS001..RS055
production_authority_granted: false
source_adapters_are_evidence_retrieval_only: true
status_and_version_are_first_class: true
~~~
