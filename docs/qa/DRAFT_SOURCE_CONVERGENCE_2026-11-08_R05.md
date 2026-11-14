# Draft source convergence R05 — exact source custody

**DRAFT / REVIEW-ONLY / NO MERGE / NO RELEASE.** Parent #5089 SHA `9dbaae5266fbd37f84f61b01e9adc14de4fe81d0`. Six historic owner-derived source PRs; parent holds remain active. Source SHA below is reused exactly and is not a runtime certification. 53 selected donor paths; 7 same-SHA governed Jeeves mirror paths. Canonical AIFT-JEEVES source-tree SHA must be recalculated from the post-stage Git tree. No ownership cutover authorized.

## Selected original source paths
- #5020: `skeleton/jeeves/worlds/world_canon.py` — modified `e6d6891196ba4bc789574f34957293c84faa34f9`
- #5020: `skeleton/jeeves/worlds/world_delivery_cli.py` — added `1c89e8a03bd94a1aec47e86f34b07a5f4944c299`
- #5020: `skeleton/jeeves/worlds/world_edit_cli.py` — added `fc817e5b7372f21933fc1a91e93c0598f3c95cb1`
- #5020: `skeleton/jeeves/worlds/world_handoff_cli.py` — added `71289f8a52c94cf87086b9341d7ef27102ed6c5e`
- #5020: `skeleton/jeeves/worlds/world_reviewed_delivery.py` — added `05d838ac73734e36dbcb6c217051857dad8bdd6c`
- #5020: `skeleton/jeeves/worlds/world_session.py` — added `4e6a6d6e706d3b41a4a39c8664f5c84569e63db0`
- #5020: `skeleton/jeeves/worlds/world_session_cli.py` — added `d9acc801efac841d2b2dab207c682c6c31493719`
- #5020: `skeleton/testing/test_world_delivery_cli.py` — added `5e6ce6dfc9787384b8d942e7f9eeb47ffa1e1aba`
- #5020: `skeleton/testing/test_world_handoff_cli.py` — added `76c4dbd52332c4e95d421862dc39c7ca6bc82e0d`
- #5020: `skeleton/testing/test_world_playable_session_contract.py` — added `85d168b028d047dedc624585bae319dda3e085b1`
- #5020: `skeleton/testing/test_world_reviewed_delivery.py` — added `2ac8ac087a2ff3b956779505c8fe208a5b74a578`
- #5020: `skeleton/testing/test_world_reviewed_edit_cli.py` — added `51358b3e38170657931769c270551ecba3a7879a`
- #5020: `skeleton/testing/test_world_session_cli.py` — added `c3f5ac58c7e82ed41e971dee6ae7ed6808531c34`
- #5020: `skeleton/testing/test_world_session_portable_io.py` — added `4797f2ddeb6b3898f4e16c3276561c076fa2932c`
- #5020: `skeleton/testing/test_world_session_replay.py` — added `8539ed1081fda1e800db0090164baa7fedc3cc0f`
- #5020: `skeleton/testing/test_world_state_liveness.py` — added `9c0520c4a7c75fe298dc5d6006c825a1ef9d8e9d`
- #4878: `skeleton/ai/webcrawler/archive_catalog_common.py` — added `2c87fe4c081a5854fc8074fb060c89ddbdd57220`
- #4878: `skeleton/ai/webcrawler/core.py` — modified `41bf8301dcfd2a78be3b7a995bb111193a74c726`
- #4878: `skeleton/ai/webcrawler/document_formats.py` — modified `0c8b722fc32f502ef36448f8a24e5d33f19b8451`
- #4878: `skeleton/ai/webcrawler/federated_activity.py` — modified `650ad7299ce21a9154dc8bcb0ccb922c17fface1`
- #4878: `skeleton/ai/webcrawler/iiif_discovery.py` — added `4ff688417af700da7c69906cc7f8b3ecee10b250`
- #4878: `skeleton/ai/webcrawler/iiif_manifest_documents.py` — added `12439380bf158450eead2305bb95f74fed911533`
- #4878: `skeleton/ai/webcrawler/oai_pmh_discovery.py` — added `ea3540515471640d1f038dc9d70abddcab22092e`
- #4878: `skeleton/ai/webcrawler/opds_discovery.py` — added `108822bd6dcef84a3907819ba95c7274347331b8`
- #4878: `skeleton/ai/webcrawler/operations.py` — modified `79a98c996d259d4839d512603a809bb47a8328bd`
- #4878: `skeleton/ai/webcrawler/structured_discovery.py` — modified `63acb6d7d198013ed3fb106321597fc55706effe`
- #4878: `tests/test_ai_webcrawler_dragon_activitystreams.py` — modified `bc080489ec47db2f5d9d308f5abc40f606219446`
- #4878: `tests/test_ai_webcrawler_dragon_archive_catalogs.py` — added `d502c29a1019052877f1b8f4a593cbf679eba0ee`
- #4895: `.github/workflows/vol249-250-research-reasoning.yml` — added `1fe51ddbf05034d126e4a096a88981b5f82cb3ac`
- #4895: `docs/ai/VOL_249_250_RESEARCH_REASONING.md` — added `0918b761707c58b7f7a4c8c00d3cb3fe1a53b5c0`
- #4895: `skeleton/ai/research/causal_knowledge.py` — added `92d8e868ddb73ccaedd988bfffc64f4a09f232fe`
- #4895: `skeleton/ai/research/game_design_probes.py` — added `137425b8111a1462ee1b9acb6105dbba0105be1c`
- #4895: `skeleton/ai/research/hypothesis_engine.py` — added `a3b2b98863dc5346b6dc2a8e5c4d71df975075aa`
- #4895: `skeleton/testing/test_ai_flight_context_admission.py` — modified `ff4bb33e9c150763da41e6cd2b764d8ddf1ba856`
- #4895: `skeleton/testing/test_ai_flight_http.py` — modified `c2337de1e9eb2aaeec7c247f9ab27ac8718d5f50`
- #4895: `skeleton/testing/test_ai_git_knowledge.py` — modified `6c0996e86d589422c3e80a2b14949ac2dec6becf`
- #4895: `skeleton/testing/test_ai_knowledge_plane.py` — modified `5a6ebcdf0eb5f3cd0e20e4d7087a0fd1338436cd`
- #4895: `skeleton/testing/test_ai_native_daemon.py` — modified `1d3a617cf00d7e27375164a3fdd78a7c32d9930c`
- #4895: `skeleton/testing/test_causal_knowledge.py` — added `050eb7333343d466744a0775afe6470203055510`
- #4895: `skeleton/testing/test_game_design_probes.py` — added `60be9b04d90f1c9a33ebbd6bddcc38f6369cc1aa`
- #4895: `skeleton/testing/test_hypothesis_engine.py` — added `db28033802514095687116bce183e0291d706304`
- #4895: `skeleton/testing/test_jeeves_native_durable_cli.py` — modified `8d41d55b9be3dc1c3e86809cd15b1b18a960e044`
- #4880: `GROKBOT_FIRST.md` — added `0fcbc1b7ce659d77f375cc8e613f0f732dd90065`
- #4867: `backend/core/discourse_catalog.py` — added `b15cdae73f6c58baa13ff82b2d9e922a92c10bae`
- #4867: `backend/tests/test_discourse_admission_fairness.py` — added `9954699bb300d7d1f0057e2cb1b8b0452d3f804c`
- #4867: `backend/tests/test_discourse_canonical_dispatch.py` — added `88579479794dfe068d65fafce9d951d765f56562`
- #4867: `backend/tests/test_discourse_job_discovery.py` — added `1d85d0985d6fc239338a87fdd18729a179a12c9e`
- #4867: `backend/tests/test_discourse_judge_budget.py` — added `00ff2fecc568c1f455b1ff0e32b28391f6a0c13e`
- #4867: `backend/tests/test_discourse_worker_continuity.py` — added `7a774b7d546e1141e181e782bcc442376eb02e61`
- #4867: `frontend/scripts/test-discourse-async-jobs.mjs` — added `48a6d03d2c32487824da184859febce2b7b94d48`
- #4867: `frontend/src/features/discourse/discourseJob.ts` — added `dcd31c7003ceb7fc164387e3114703fda74fbeaa`
- #4879: `.github/workflows/jeeves-atomic-review-regression.yml` — added `0c7d930edb07478da09a5653da29b01137e78b32`
- #4879: `skeleton/testing/test_jeeves_laptop_atomic_review.py` — added `4c2412cf85cea28bf71c16b0d8e5058434da4c25`

## Exclusions / duplicate custody
- #4878 `.github/workflows/dragon-campaign-source-tests.yml` — Already integrated into parent
- #4878 `docs/ai/DRAGON_WAVE24_ARCHIVE_RESEARCH_PROTOCOLS.md` — Already integrated into parent
- #4867 `backend/routes/discourse.py` — Do not replace earlier tenant authentication / frontend implementations
- #4867 `backend/tests/test_discourse.py` — Do not replace earlier tenant authentication / frontend implementations
- #4867 `backend/tests/test_discourse_judge_admission.py` — Do not replace earlier tenant authentication / frontend implementations
- #4867 `backend/tests/test_discourse_live.py` — Do not replace earlier tenant authentication / frontend implementations
- #4867 `backend/tests/test_discourse_tenant_authority.py` — Do not replace earlier tenant authentication / frontend implementations
- #4867 `frontend/app/discourse.tsx` — Do not replace earlier tenant authentication / frontend implementations
- #4867 `frontend/package.json` — Do not replace earlier tenant authentication / frontend implementations
- #4879 `skeleton/jeeves/worlds/laptop_flow.py` — Leave laptop_flow.py modification to independent source-security review

The #5020 Jeeves world_canon revision is retained; #4893 and #4897 alternative world_canon source versions must not be double-copied. #4867 copies **new files only**, retaining parent discourse auth and TLS controls rather than replacing them with historic branch versions. #4879's reviewed writer lease modification is not installed on this branch. Upstream #5081/#5074, source rights and all mandatory exact-head CI, tenant, source parity, safety/security, signed provenance, Windows, device, GGUF, Docker, Godot and release holds remain unchanged.
