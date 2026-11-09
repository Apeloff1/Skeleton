"""
Advanced knowledge collections (2026-05 phase 4):
  • code_similarity_logic        — fingerprint detectors for code similarity
  • asset_engine_theft           — asset & engine theft signatures
  • game_playing_logic_clones    — known clone-game pairs (Flappy Bird et al.)
  • ast_detection                — AST-shape detectors
  • mechanic_legal_paradox       — 'idea-vs-expression' jurisprudence rows
  • stylometric_fingerprint      — feature set used to author-identify code
  • academic_frameworks          — papers/frameworks the pipeline cites
  • linting_formatters           — linter configs per language
  • stylometric_features         — quantified feature engineering rows
  • agnostic_content_index       — license-clean content provenance
  • training_recipes             — cross-entropy custom losses + fine-tune + log-probs
  • scraper_jobs                 — cron-job manifest for live freshness
"""
from __future__ import annotations
import hashlib, logging, itertools
from datetime import datetime, timezone

log = logging.getLogger("knowledge.phase4")

def _h(*p): return hashlib.md5("|".join(p).encode()).hexdigest()[:14]

# ─── 1. code_similarity_logic ────────────────────────────────────────
SIM_TECHNIQUES = [
    ("token-shingle-jaccard",   "k-shingle of tokens, Jaccard over sets"),
    ("winnowing-fingerprint",   "Winnowing algorithm (Moss/JPlag heritage)"),
    ("ast-edit-distance",       "Tree-edit-distance on canonicalised AST"),
    ("cpg-graph-matching",      "Code-property-graph subgraph isomorphism"),
    ("control-flow-hash",       "Hash of CFG node-types ignoring identifiers"),
    ("normalized-compression",  "Normalized compression distance (NCD/zlib)"),
    ("sequence-alignment",      "Smith-Waterman on token sequences"),
    ("embedding-cosine",        "Cosine on CodeBERT/UnixCoder embeddings"),
    ("behavioural-fuzz",        "Cross-fuzzing input-output equivalence"),
    ("slicing-trace",           "Backward slicing on tainted I/O"),
]
LANGS = ["Python","JavaScript","TypeScript","C#","C++","Rust","Go","Java","Lua","GDScript"]

def build_code_similarity():
    out=[]
    for (t,desc),lang in itertools.product(SIM_TECHNIQUES, LANGS):
        out.append({"id":"sim_"+_h(t,lang),"technique":t,"language":lang,"description":desc,
                    "thresholds":{"low":0.30,"medium":0.55,"high":0.78,"identical":0.95},
                    "tags":[t,lang.lower(),"similarity","detection"]})
    return out

async def seed_code_similarity(db):
    docs = build_code_similarity()
    try:
        await db.code_similarity_logic.create_index("id", unique=True)
        await db.code_similarity_logic.create_index("technique")
        await db.code_similarity_logic.create_index("language")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.code_similarity_logic.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.code_similarity_logic.count_documents({})}

# ─── 2. asset_engine_theft ───────────────────────────────────────────
THEFT_SIGNATURES = [
    ("texture-perceptual-hash",   "pHash on texture set; <8 bit diff = likely lift"),
    ("mesh-vertex-hash",          "Hash of sorted vertex positions + topology hash"),
    ("audio-fingerprint",         "Chromaprint/Shazam-style audio fingerprint"),
    ("shader-bytecode-hash",      "DXBC/SPIR-V bytecode hash modulo names"),
    ("font-glyph-hash",           "per-glyph SDF hash"),
    ("animation-clip-trajectory", "Bone-trajectory cosine over normalized time"),
    ("engine-signature-strings",  "Find embedded engine version strings"),
    ("unity-defaults",            "Default Unity sphere/cube hashes"),
    ("ue-default-mannequin",      "UE Mannequin skeleton DNA hash"),
    ("asset-store-pack-id",       "Detect Asset Store guid + version"),
    ("reverse-engineered-pak",    "PAK structure with known compression headers"),
    ("unity-il2cpp-metadata",     "il2cpp metadata strings revealing original namespaces"),
]
ENGINES = ["Unity","Unreal","Godot","GameMaker","Cocos","Defold","Phaser","Construct","O3DE","Stride"]

def build_asset_theft():
    out=[]
    for (sig,desc),engine in itertools.product(THEFT_SIGNATURES, ENGINES):
        out.append({"id":"theft_"+_h(sig,engine),"signature":sig,"engine":engine,"description":desc,
                    "severity":"high" if "hash" in sig or "engine" in sig else "medium",
                    "tags":[sig,engine.lower(),"theft","detection"]})
    return out

async def seed_asset_theft(db):
    docs=build_asset_theft()
    try:
        await db.asset_engine_theft.create_index("id", unique=True)
        await db.asset_engine_theft.create_index("signature")
        await db.asset_engine_theft.create_index("engine")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.asset_engine_theft.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.asset_engine_theft.count_documents({})}

# ─── 3. game_playing_logic_clones ────────────────────────────────────
KNOWN_CLONE_PAIRS = [
    ("Flappy Bird",          "Helicopter (2004), 1-button auto-scroller",          "protected: 'art-style' only; mechanic in PD"),
    ("Threes!",              "2048",                                                "loss: 2048 mechanic deemed unprotectable"),
    ("Tetris",               "Mino, Tetris Clones",                                 "Tetris Co. wins on visual likeness, not rules"),
    ("PUBG",                 "Garena Free Fire (alleged)",                          "settled out of court"),
    ("Atari Asteroids",      "Computer Space sequels",                              "public domain after expiry"),
    ("Pong",                 "countless",                                            "PD"),
    ("Doom",                 "Heretic (id-licensed), Strife",                        "licensed clones"),
    ("Spelunky",             "Spelunky Classic clones in HTML5",                    "creator open-sourced"),
    ("Among Us",             "Goose Goose Duck etc.",                                "settled / coexist"),
    ("Stardew Valley",       "Harvest Moon homage",                                  "genre conventions allowed"),
    ("Vampire Survivors",    "Survivors.io and dozens of mobile clones",            "mechanic public; art style protected"),
    ("Wordle",               "hundreds of language clones",                          "NYT lawsuits limited to direct copies"),
    ("Slay the Spire",       "hundreds of deck-builder clones",                     "design pattern shared widely"),
    ("Minecraft",            "Eldercraft, Trove, Hytale etc.",                       "Mojang focuses on trademarks, not mechanics"),
]
ASPECTS = ["art","mechanic","audio","story","trademark","code"]

def build_clones():
    out=[]
    for (orig,clone,notes),aspect in itertools.product(KNOWN_CLONE_PAIRS, ASPECTS):
        out.append({"id":"clone_"+_h(orig,clone,aspect),"original":orig,"clone":clone,
                    "aspect":aspect,"legal_notes":notes,
                    "protected":"yes" if aspect in ("art","audio","story","trademark") else "limited",
                    "tags":["clone",aspect,orig.lower().split()[0]]})
    return out

async def seed_clones(db):
    docs=build_clones()
    try:
        await db.game_playing_logic_clones.create_index("id", unique=True)
        await db.game_playing_logic_clones.create_index("original")
        await db.game_playing_logic_clones.create_index("aspect")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.game_playing_logic_clones.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.game_playing_logic_clones.count_documents({})}

# ─── 4. ast_detection ────────────────────────────────────────────────
AST_DETECTORS = [
    ("identifier-rename-invariant", "Hash AST with identifiers canonicalised to V<n>"),
    ("control-flow-skeleton",       "Strip leaves; hash internal node-type sequence"),
    ("function-call-graph",         "Build call-graph + hash edge multiset"),
    ("loop-nesting-profile",        "Vector of loop-depth at each statement"),
    ("reaching-defs-shape",         "Hash of reaching-definitions sets"),
    ("basic-block-types",           "BB-type sequence as n-gram fingerprint"),
    ("sub-tree-mining",             "Top-k frequent sub-trees as feature vector"),
    ("datalog-shape-query",         "Encode as datalog predicates; pattern-match"),
]

def build_ast_detect():
    out=[]
    for (d,desc),lang in itertools.product(AST_DETECTORS, LANGS):
        out.append({"id":"ast_"+_h(d,lang),"detector":d,"language":lang,"description":desc,
                    "tags":[d,lang.lower(),"ast","detection"]})
    return out

async def seed_ast_detect(db):
    docs=build_ast_detect()
    try:
        await db.ast_detection.create_index("id", unique=True)
        await db.ast_detection.create_index("detector")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.ast_detection.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.ast_detection.count_documents({})}

# ─── 5. mechanic_legal_paradox ───────────────────────────────────────
PRECEDENTS = [
    ("Atari v. Amusement World",        1981, "Asteroids vs. Meteors",            "merger doctrine: idea-mechanic unprotected"),
    ("Tetris v. Xio",                   2012, "clone copied size + colours of bricks","victory: protected expression of mechanic"),
    ("Spry Fox v. LOL",                 2012, "Triple Town vs. Yeti Town",         "settled; gameplay idea protectable when expression copied"),
    ("DaVinci Editrice v. Ziko",        2016, "Bang! vs. Legends of the Three Kingdoms","copyright protects expression, not 'game mechanics'"),
    ("Capcom v. Data East",             1994, "Street Fighter vs. Fighter's History","loss: 'idea' not protectable"),
    ("Atari v. Williams",               1981, "Defender vs. Stargate",             "loss: mechanic alone unprotectable"),
    ("Sega v. Accolade",                1992, "reverse-engineering for compatibility","fair use under 17 USC § 117"),
    ("Lewis Galoob v. Nintendo",        1992, "Game Genie modifying gameplay",     "derivative-work claim rejected"),
    ("Blizzard v. BnetD",               2005, "reverse-engineering battle.net",    "DMCA anti-circumvention applied"),
    ("Bethesda v. Mojang",              2011, "Scrolls vs. Elder Scrolls",         "trademark settlement"),
]

def build_legal_paradox():
    out=[]
    for case,year,facts,outcome in PRECEDENTS:
        out.append({"id":"legal_"+_h(case,str(year)),"case":case,"year":year,"facts":facts,
                    "outcome":outcome,"description":f"{case} ({year}): {facts} — {outcome}",
                    "tags":[case.lower().split()[0],"legal","precedent","mechanic"]})
    return out

async def seed_legal_paradox(db):
    docs=build_legal_paradox()
    try:
        await db.mechanic_legal_paradox.create_index("id", unique=True)
        await db.mechanic_legal_paradox.create_index("case")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.mechanic_legal_paradox.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.mechanic_legal_paradox.count_documents({})}

# ─── 6. stylometric_fingerprint ──────────────────────────────────────
STYLOMETRIC = [
    ("avg-line-length",        "Avg chars per non-empty line"),
    ("indentation-style",      "Tabs vs spaces vs mixed"),
    ("brace-style",            "K&R / Allman / GNU / 1TBS"),
    ("identifier-snake-ratio", "snake_case / total identifiers"),
    ("identifier-camel-ratio", "camelCase / total identifiers"),
    ("comment-density",        "comments / non-blank lines"),
    ("todo-fixme-rate",        "TODO+FIXME per kloc"),
    ("max-nesting-depth",      "Max if/for nesting"),
    ("avg-function-length",    "Avg lines per fn"),
    ("cyclomatic-complexity",  "McCabe per fn (avg)"),
    ("halstead-vocabulary",    "Distinct operator + operand count"),
    ("halstead-volume",        "Halstead V metric"),
    ("unique-keyword-ratio",   "distinct keywords / lines"),
    ("string-length-mean",     "avg chars per string literal"),
    ("docstring-presence",     "% functions with docstrings"),
    ("type-hint-density",      "% parameters with type hints"),
    ("early-return-rate",      "early returns / total returns"),
    ("throws-vs-rejects",      "raise/throw count per kloc"),
    ("import-count-mean",      "avg imports/module"),
    ("empty-line-density",     "blank lines / total lines"),
    ("shebang-presence",       "% scripts with shebang"),
    ("trailing-comma-style",   "trailing commas in collections?"),
    ("single-vs-double-quote", "' vs \" preference"),
    ("f-string-vs-format",     "% f-string vs .format()/%"),
    ("naming-anglo-ratio",     "English words / total identifier tokens"),
]

def build_stylometric():
    out=[]
    for (f,desc),lang in itertools.product(STYLOMETRIC, LANGS):
        out.append({"id":"sty_"+_h(f,lang),"feature":f,"language":lang,"description":desc,
                    "tags":[f,lang.lower(),"stylometric","fingerprint"]})
    return out

async def seed_stylometric(db):
    docs=build_stylometric()
    try:
        await db.stylometric_fingerprint.create_index("id", unique=True)
        await db.stylometric_fingerprint.create_index("feature")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.stylometric_fingerprint.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.stylometric_fingerprint.count_documents({})}

# ─── 7. academic_frameworks ──────────────────────────────────────────
FRAMEWORKS = [
    ("GameRefinementTheory",     "Iida, 2003+",      "GR-value formula for engagement"),
    ("MDA",                       "Hunicke 2004",    "Mechanics-Dynamics-Aesthetics"),
    ("FlowTheory",               "Csikszentmihalyi 1990","Skill vs challenge balance"),
    ("BartleTypes",              "Bartle 1996",      "Achiever/Explorer/Socializer/Killer"),
    ("OctalysisFramework",       "Yu-kai Chou 2015", "8 core drives of gamification"),
    ("Self-DeterminationTheory", "Deci & Ryan 1985", "Autonomy / Competence / Relatedness"),
    ("PERMA-V",                  "Seligman 2011+",   "Positive emotion / Engagement / Relationships / Meaning / Accomplishment / Vitality"),
    ("DesignThinking",           "IDEO 2000s",       "Empathy → Define → Ideate → Prototype → Test"),
    ("CoreLoopAnalysis",         "Schreiber 2010",   "Micro / Meso / Macro loops"),
    ("AffordanceTheory",         "Gibson 1979 / Norman 1988","Perceived affordances drive interaction"),
    ("InformationTheoryGames",   "Shannon 1948 applied","Mutual-information of choice space"),
    ("PlayerExperienceOfNeedSatisfaction","Ryan 2006 (PENS)","Validated questionnaire for self-determination"),
    ("GameDesignPatternsLibrary","Björk & Holopainen 2005","Hundreds of structural patterns"),
    ("CodeReviewBenchmark-HumanEval","OpenAI 2021","Code synthesis benchmark"),
    ("MBPP",                      "Austin 2021",     "Mostly Basic Python Problems"),
    ("BigCodeBench",             "BigCode 2024",     "1000+ practical Python tasks"),
    ("SWE-bench",                 "Princeton 2023",  "Real-world bug-fix benchmark"),
    ("LiveCodeBench",            "Berkeley 2024",    "Contamination-free coding eval"),
    ("GameBench",                "DeepMind 2023",    "Generalist agent eval suite"),
    ("MineDojo",                 "Fan 2022",         "Minecraft open-ended benchmark"),
]

def build_academic():
    out=[]
    for name,author,desc in FRAMEWORKS:
        out.append({"id":"ac_"+_h(name),"name":name,"author":author,"description":desc,
                    "tags":[name.lower(),"framework","academic"]})
    return out

async def seed_academic(db):
    docs=build_academic()
    try:
        await db.academic_frameworks.create_index("id", unique=True)
        await db.academic_frameworks.create_index("name")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.academic_frameworks.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.academic_frameworks.count_documents({})}

# ─── 8. linting_formatters ───────────────────────────────────────────
LINTERS = {
    "Python":      [("ruff",       "line-length=120, isort, pep8"),("black",     "line-length=120"),("mypy",      "strict")],
    "JavaScript":  [("eslint",     "airbnb-base + prettier"),     ("prettier",  "semi=true,singleQuote=false")],
    "TypeScript":  [("eslint",     "@typescript-eslint/strict"), ("prettier",  "semi=true,singleQuote=false"),("tsc","--strict")],
    "Rust":        [("rustfmt",    "edition=2021"),               ("clippy",    "-Dwarnings")],
    "Go":          [("gofmt",      ""),("golangci-lint","--enable-all")],
    "C#":          [("dotnet-format","--check"),("roslynator",   "strict")],
    "C++":         [("clang-format","BasedOnStyle: LLVM"),("cpplint","--filter=-build")],
    "Java":        [("google-java-format","--aosp"),("checkstyle","google_checks.xml")],
    "Kotlin":      [("ktlint",     "")],
    "Swift":       [("swiftformat","--swiftversion 5.10"),("swiftlint","strict")],
    "Lua":         [("luacheck",   "--no-unused-args")],
    "GDScript":    [("gdformat",   ""),("gdlint","")],
    "GLSL":        [("glslang",    "-l")],
    "HLSL":        [("dxc",        "-Vd")],
}

def build_linting():
    out=[]
    for lang, tools in LINTERS.items():
        for tool,opts in tools:
            out.append({"id":"lint_"+_h(lang,tool),"language":lang,"tool":tool,"options":opts,
                        "description":f"{tool} for {lang} — opts: {opts}",
                        "tags":[lang.lower(),tool,"lint","format"]})
    return out

async def seed_linting(db):
    docs=build_linting()
    try:
        await db.linting_formatters.create_index("id", unique=True)
        await db.linting_formatters.create_index("language")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.linting_formatters.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.linting_formatters.count_documents({})}

# ─── 9. agnostic_content_index ───────────────────────────────────────
AGNOSTIC_SOURCES = [
    ("OpenGameArt-CC0",            "CC0",     "Sprites, music, tilesets"),
    ("FreeSound-CC0",              "CC0",     "SFX library"),
    ("Kenney.nl",                  "CC0",     "Massive low-poly + 2D asset packs"),
    ("Quaternius",                 "CC0",     "Low-poly 3D models"),
    ("GameDev Market FREE",        "varied",   "Curated free packs"),
    ("itch.io free assets",        "varied",   "Filter by 'free' + license tag"),
    ("Sketchfab CC",               "CC-BY/0", "3D model library"),
    ("Polyhaven",                  "CC0",     "HDRIs + PBR materials"),
    ("AmbientCG",                  "CC0",     "Material library"),
    ("Mixamo",                     "royalty-free","Rigged characters + animations"),
    ("Soundimage.org",             "CC-BY",   "Music + SFX"),
    ("OpenAir Acoustic Impulses",  "CC-BY-SA","Reverb impulse responses"),
    ("Wikimedia Commons",          "varied",   "Public-domain media"),
    ("Project Gutenberg",          "PD",      "Public-domain text"),
    ("NASA Image Library",         "PD",      "Imagery + audio"),
]

def build_agnostic():
    out=[]
    for source,lic,desc in AGNOSTIC_SOURCES:
        out.append({"id":"agc_"+_h(source),"source":source,"license":lic,"description":desc,
                    "tags":[source.lower().split('.')[0],"agnostic","content"]})
    return out

async def seed_agnostic(db):
    docs=build_agnostic()
    try:
        await db.agnostic_content_index.create_index("id", unique=True)
        await db.agnostic_content_index.create_index("source")
        await db.agnostic_content_index.create_index("license")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.agnostic_content_index.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.agnostic_content_index.count_documents({})}

# ─── 10. training_recipes ────────────────────────────────────────────
TRAINING_RECIPES = [
    ("cross-entropy-token",        "Standard token-level CE loss"),
    ("cross-entropy-label-smooth", "Label smoothing 0.1 on next-token CE"),
    ("cross-entropy-focal",        "Focal-CE on rare tokens: (1-p)^2 * CE"),
    ("cross-entropy-curriculum",   "Stage-wise: easy → hard examples by perplexity"),
    ("loss-mask-system-prompt",    "Zero-out loss on system & boilerplate tokens"),
    ("loss-mask-paste-block",      "Zero-out loss on pasted code regions to avoid memorisation"),
    ("loss-mix-style-and-task",    "0.7*task-CE + 0.3*stylometric-CE"),
    ("DPO",                         "Direct preference optimization on pairs"),
    ("ORPO",                        "Odds-ratio preference optimization"),
    ("KTO",                         "Kahneman-Tversky optimization"),
    ("LoRA-r=16",                  "Low-rank adapter rank 16, alpha 32"),
    ("QLoRA-4bit",                 "4-bit base + LoRA adapters"),
    ("full-finetune",              "All params trainable, low LR"),
    ("instruction-tune-sft",       "Supervised fine-tune on (instr, response)"),
    ("rejection-sampling",         "Sample N, keep top-k by reward model"),
    ("in-context-log-probs-eval",  "Eval by log-prob of correct continuation given few-shot context"),
    ("in-context-self-consistency","Sample k chains, majority-vote"),
    ("in-context-tree-search",     "MCTS over tree of partial generations"),
]

def build_training():
    out=[]
    for name,desc in TRAINING_RECIPES:
        out.append({"id":"train_"+_h(name),"recipe":name,"description":desc,
                    "tags":[name.lower(),"training","recipe"]})
    return out

async def seed_training(db):
    docs=build_training()
    try:
        await db.training_recipes.create_index("id", unique=True)
        await db.training_recipes.create_index("recipe")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.training_recipes.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.training_recipes.count_documents({})}

# ─── 11. scraper_jobs (manifest) ─────────────────────────────────────
SCRAPER_JOBS = [
    ("steam-patch-notes",       "GET https://store.steampowered.com/news/app/{appid}","daily"),
    ("liquipedia-patches",      "GET https://liquipedia.net/{game}/Patch_Notes",     "daily"),
    ("github-trending",         "GET https://github.com/trending?since=daily",         "daily"),
    ("github-search-game",      "GET https://api.github.com/search/repositories?q=game+language:rust+stars:>1000","weekly"),
    ("wayback-archive",         "GET http://archive.org/wayback/available?url={url}",  "weekly"),
    ("steamdb-feed",            "GET https://steamdb.info/api/PatchnotesRSS/",        "daily"),
    ("reddit-gamedev",          "GET https://reddit.com/r/gamedev/top.json?t=day",   "daily"),
    ("hackernews-frontpage",    "GET https://hacker-news.firebaseio.com/v0/topstories.json","hourly"),
    ("unity-blog",              "GET https://blog.unity.com/feed",                    "weekly"),
    ("unreal-blog",             "GET https://www.unrealengine.com/en-US/feed",         "weekly"),
    ("godot-blog",              "GET https://godotengine.org/rss.xml",                "weekly"),
    ("itchio-trending",         "GET https://itch.io/games",                          "daily"),
]

def build_scraper_jobs():
    out=[]
    for name,endpoint,cadence in SCRAPER_JOBS:
        out.append({"id":"job_"+_h(name),"name":name,"endpoint":endpoint,"cadence":cadence,
                    "enabled":False,  # off by default; live scrape requires user opt-in + rate-limit policy
                    "last_run_at":None,"last_run_status":None,
                    "description":f"{cadence} scrape from {endpoint.split(' ')[1] if ' ' in endpoint else endpoint}",
                    "tags":[name,cadence,"scraper"]})
    return out

async def seed_scraper_jobs(db):
    docs=build_scraper_jobs()
    try:
        await db.scraper_jobs.create_index("id", unique=True)
        await db.scraper_jobs.create_index("name")
        await db.scraper_jobs.create_index("enabled")
    except: pass
    n=datetime.now(timezone.utc).isoformat(); ins=0
    for d in docs:
        d["indexed_at"]=n
        try:
            r=await db.scraper_jobs.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: ins+=1
        except: pass
    return {"inserted":ins,"total":await db.scraper_jobs.count_documents({})}

# ─── Master kicker ───────────────────────────────────────────────────
async def seed_phase4_all(db) -> dict:
    out = {}
    for label, fn in [
        ("code_similarity_logic",       seed_code_similarity),
        ("asset_engine_theft",          seed_asset_theft),
        ("game_playing_logic_clones",   seed_clones),
        ("ast_detection",               seed_ast_detect),
        ("mechanic_legal_paradox",      seed_legal_paradox),
        ("stylometric_fingerprint",     seed_stylometric),
        ("academic_frameworks",         seed_academic),
        ("linting_formatters",          seed_linting),
        ("agnostic_content_index",      seed_agnostic),
        ("training_recipes",            seed_training),
        ("scraper_jobs",                seed_scraper_jobs),
    ]:
        try: out[label] = await fn(db)
        except Exception as e: out[f"{label}_error"] = str(e)[:200]
    log.info(f"[phase4] all-in-one seeding result: {out}")
    return out
