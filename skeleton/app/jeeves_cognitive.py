"""Bounded, source-bound cognitive preflight for the installed Jeeves chat.

This module is deliberately advisory: it does not rewrite prompts, authorize
tools, create memories, perform generation or score model intelligence.
Conversation evidence is read from the caller's already verified session.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import math
import re
import unicodedata

SCHEMA = "skeleton.jeeves.cognitive-preview.v1"
MAX_HISTORY_SCAN = 128
MAX_MEMORY_RESULTS = 6
MAX_CLAUSES = 8
MAX_TEXT_CHARS = 4096
_WORD = re.compile(r"[^\W_]+(?:[-_.][^\W_]+)*", re.UNICODE)
_SPLIT = re.compile(r"(?:[\n;]+|(?<=[?!。！？])\s*|(?<=\.)\s+)")
_STOP = frozenset("a an the and or of to in on for by with is are was were "
                  "this that it be as from what why how when where can could "
                  "would should please me my you your i we do does did".split())
_CUES = {
    "code": {"code", "debug", "implement", "compile", "test", "refactor", "python", "typescript", "bug"},
    "research": {"research", "compare", "sources", "evidence", "verify", "cite", "investigate"},
    "planning": {"plan", "design", "roadmap", "steps", "architecture", "dependencies"},
    "creative": {"write", "story", "invent", "brainstorm", "character", "dialogue"},
    "game": {"game", "quest", "scene", "godot", "unity", "unreal", "level", "npc"},
    "analysis": {"analyze", "analyse", "calculate", "evaluate", "explain", "reason", "tradeoffs"},
    "memory": {"remember", "previous", "earlier", "continue", "recall", "last"},
    "media": {"image", "audio", "video", "photo", "transcript", "ocr"},
}
_WORKFLOW = {
    "code": ("inspect_existing_source", "propose_bounded_change", "verify_with_tests"),
    "research": ("retrieve_authorized_sources", "compare_evidence", "report_uncertainty"),
    "planning": ("identify_constraints", "order_dependencies", "define_acceptance"),
    "creative": ("identify_style_constraints", "draft_alternatives", "review_consistency"),
    "game": ("inspect_project_constraints", "design_playable_loop", "validate_game_state"),
    "analysis": ("identify_assumptions", "evaluate_alternatives", "check_conclusion"),
    "memory": ("retrieve_exact_prior_user_text", "check_revision", "request_review"),
    "media": ("inspect_reviewed_advisory", "identify_missing_modalities", "review_source"),
    "general": ("answer_request", "check_instruction_coverage"),
}


def _pin(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _hash(text):
    return sha256(text.encode("utf-8")).hexdigest()


def _canonical_hash(value):
    return _hash(json.dumps(value, ensure_ascii=True, sort_keys=True,
                            separators=(",", ":"), allow_nan=False))


def _terms(text):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return tuple(word for word in _WORD.findall(normalized)
                 if 1 < len(word) <= 96 and word not in _STOP)[:512]


def _validate_text(text, label, maximum=MAX_TEXT_CHARS):
    if (type(text) is not str or not text.strip() or len(text) > maximum
            or "\x00" in text):
        raise ValueError("invalid " + label)
    try:
        text.encode("utf-8", errors="strict")
    except UnicodeError:
        raise ValueError("invalid Unicode in " + label) from None
    return text


def _integer(value, label, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError("invalid " + label)
    return value


def _span(start, end, text):
    return {"start": start, "end": end, "text": text[start:end],
            "sha256": _hash(text[start:end])}


def clauses(question):
    """Exact code-point spans; never turn quoted text into executable tasks."""
    result = []
    cursor = 0
    for match in _SPLIT.finditer(question):
        start, end = cursor, match.start()
        cursor = match.end()
        while start < end and question[start].isspace():
            start += 1
        while end > start and question[end - 1].isspace():
            end -= 1
        if end > start:
            result.append(_span(start, end, question))
        if len(result) == MAX_CLAUSES - 1:
            # Last span preserves the remaining request, rather than dropping
            # trailing constraints during decomposition.
            break
    if cursor < len(question):
        start, end = cursor, len(question)
        while start < end and question[start].isspace():
            start += 1
        while end > start and question[end - 1].isspace():
            end -= 1
        if end > start:
            result.append(_span(start, end, question))
    return result


# Explicit multilingual intent vocabulary, normalized before overlap.
# These are bounded routing signals, not translation or language detection.
_MULTILINGUAL_CUES = {
    "code": "kode programmering feilretting implementer test kodefeil programmieren debuggen implementieren code programmer déboguer implementar programar depurar código corrigir 编程 代码 调试 实现 テスト コード 実装 개발 코드 구현 برمجة كود تنفيذ कोड प्रोग्रामिंग",
    "research": "forskning undersøk sammenlign kilder bevis verifiser recherchieren vergleichen quellen belege vérifier recherche comparer sources investigar comparar fuentes pesquisa fontes 研究 比较 来源 验证 調査 比較 検証 연구 비교 검증 بحث مقارنة مصادر शोध तुलना",
    "planning": "planlegg planlegging arkitektur avhengigheter planung entwerfen architektur planifier architecture dépendances planificar diseño arquitectura planejamento dependências 规划 设计 架构 依赖 計画 設計 計画立案 계획 설계 의존성 تخطيط تصميم خطة योजना डिजाइन",
    "creative": "skriv fortelling skap figur geschichte schreiben erfinden écrire histoire personnage escribir historia personaje escrever história 创作 故事 角色 物語 執筆 캐릭터 창작 이야기 قصة كتابة إبداع कहानी लेखन",
    "game": "spill oppdrag scene nivå spiel quest szene spielentwicklung jeu quête niveau juego misión nivel jogo missão 游戏 关卡 任务 ゲーム クエスト 게임 퀘스트 레벨 لعبة مهمة مستوى खेल स्तर",
    "analysis": "analyser beregn forklar vurder analysieren berechnen erklären analyser calculer expliquer analizar calcular explicar analisar calcular 计算 分析 解释 分析する 計算 説明 분석 계산 설명 تحليل حساب شرح विश्लेषण गणना",
    "memory": "husk fortsett tidligere forrige erinnerung erinnern vorher fortsetzen mémoire souvenir continuer recordar anterior continuar lembrar anterior 记忆 继续 之前 記憶 続ける 以前 기억 계속 이전 ذاكرة تذكر متابعة स्मृति याद",
    "media": "bilde lyd video foto bild audio aufnahme image audio vidéo imagen sonido vídeo imagem áudio 图片 音频 视频 画像 音声 動画 이미지 오디오 영상 صورة صوت فيديو चित्र ऑडियो",
}
_SCRIPT_CUES = frozenset({"研究", "比较", "来源", "验证", "编程", "代码", "调试", "实现",
                          "规划", "设计", "架构", "依赖", "创作", "故事", "角色",
                          "游戏", "关卡", "任务", "计算", "分析", "解释", "记忆", "继续",
                          "之前", "图片", "音频", "视频", "調査", "比較", "検証", "コード",
                          "実装", "計画", "設計", "物語", "執筆", "ゲーム", "クエスト",
                          "計算", "説明", "記憶", "続ける", "画像", "音声", "動画"})


def _roles(question):
    words = set(_terms(question))
    normalized = unicodedata.normalize("NFKC", question).casefold()
    scores = []
    for name, cues in _CUES.items():
        localized = set(_MULTILINGUAL_CUES[name].split())
        matches = words & (cues | localized)
        # CJK writing need not delimit words with spaces. Substring cues are
        # limited to an explicit language-script inventory, never Latin words.
        matches |= {cue for cue in localized & _SCRIPT_CUES if cue in normalized}
        scores.append((name, len(matches)))
    ranked = sorted((row for row in scores if row[1]), key=lambda row: (-row[1], row[0]))
    return [name for name, _ in ranked[:3]] or ["general"]


def _memory_excerpt(question, source, size=420):
    q = set(_terms(question))
    if len(source) <= size:
        return 0, len(source)
    starts = {0, len(source) - size}
    for match in _WORD.finditer(source):
        if q.intersection(_terms(match.group())):
            starts.add(min(len(source)-size, max(0, match.start()-80)))
        if len(starts) >= 256:
            break
    start = max(starts, key=lambda i: (len(q & set(_terms(source[i:i+size]))), -i))
    return start, start + size


def recall(question, messages, *, limit=MAX_MEMORY_RESULTS):
    """Rank exact prior user spans. Assistant text and system authority excluded.

    Scan at most the most recent 128 committed message rows; no learned memory,
    embeddings or persistence claims. Similarity is lexical, not truth.
    """
    _integer(limit, "memory limit", 1, MAX_MEMORY_RESULTS)
    if not isinstance(messages, (list, tuple)):
        raise ValueError("verified message sequence required")
    q = set(_terms(question))
    total = len(messages)
    lower = max(0, total - MAX_HISTORY_SCAN)
    rows = []
    for position in range(lower, total):
        message = messages[position]
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        text = message.get("content")
        if type(text) is not str or not text or len(text) > 65536:
            continue
        if "\x00" in text:
            continue
        try:
            text.encode("utf-8")
        except UnicodeError:
            continue
        words = set(_terms(text))
        common = len(q & words)
        if not common:
            continue
        score = common / math.sqrt(max(1, len(q)) * max(1, len(words)))
        start, end = _memory_excerpt(question, text)
        rows.append((score, position, {
            "message_index": position, "source_sha256": _hash(text),
            "role": "user", "lexical_similarity_ppm": round(score * 1_000_000),
            **_span(start, end, text),
            "authority": "historical-user-text-review-only",
        }))
    rows.sort(key=lambda row: (-row[0], -row[1]))
    chosen, seen = [], set()
    for _, _, row in rows:
        key = row["source_sha256"]
        if key in seen:
            continue
        chosen.append(row)
        seen.add(key)
        if len(chosen) == limit:
            break
    return {"matches": chosen, "history_rows_total": total,
            "history_rows_scanned": total-lower, "scan_truncated": lower > 0,
            "approach": "bounded-exact-lexical-recall", "automatically_injected": False}


def _evidence(question, parts, manifest):
    if manifest is None:
        return {"source_count": 0, "clause_coverage": [],
                "semantic_entailment_verified": False, "status": "not_requested"}
    citations = manifest.get("citations")
    if not isinstance(citations, list) or not 1 <= len(citations) <= 3:
        raise ValueError("invalid preview evidence")
    vocabulary = {}
    for row in citations:
        if not isinstance(row, dict):
            raise ValueError("invalid citation")
        text = _validate_text(row.get("passage"), "passage", 600)
        key = row.get("citation")
        if (type(key) is not str or not key or key in vocabulary or
                row.get("passage_sha256") != _hash(text)):
            raise ValueError("unverified preview passage")
        vocabulary[key] = set(_terms(text))
    result = []
    for part in parts:
        words = set(_terms(part["text"]))
        overlaps = sorted(({"citation": key, "matching_terms": len(words & terms)}
                          for key, terms in vocabulary.items() if words & terms),
                          key=lambda row: (-row["matching_terms"], row["citation"]))
        result.append({"start": part["start"], "end": part["end"],
                       "query_terms": len(words), "matches": overlaps,
                       "any_lexical_overlap": bool(overlaps)})
    return {"source_count": len(citations), "clause_coverage": result,
            "semantic_entailment_verified": False,
            "status": "lexical-coverage-only"}


def build_preview(question, messages, *, session_revision, model_digest,
                  tokenizer_digest, context_report, manifest=None):
    """Compose a read-only plan from the existing exact session snapshot."""
    question = _validate_text(question, "question")
    _integer(session_revision, "session revision", 0, 2**63-1)
    if not _pin(model_digest) or not _pin(tokenizer_digest):
        raise ValueError("verified model and tokenizer pins required")
    if type(context_report) is not dict:
        raise ValueError("context report required")
    total = _integer(context_report.get("context_tokens"), "context ceiling", 1, 2**31-1)
    used = _integer(context_report.get("estimated_input_tokens"), "input estimate", 1, total)
    output = _integer(context_report.get("reserved_output_tokens"), "output reserve", 1, total)
    omitted = _integer(context_report.get("omitted_history_messages"), "omitted history", 0, 2**31-1)
    if used + output > total:
        raise ValueError("context reservation exceeds ceiling")
    parts = clauses(question)
    roles = _roles(question)
    complexity = min(12, len(parts)*2 + len(roles) + min(4, len(_terms(question))//24))
    effort = "brief" if complexity <= 3 else "standard" if complexity <= 7 else "deep"
    workflows = []
    for role in roles:
        prerequisites = []
        for action in _WORKFLOW[role]:
            node = role + ":" + action
            workflows.append({"id": node, "stage": action,
                              "depends_on": prerequisites[:], "authority": "advice-only"})
            prerequisites = [node]
    memory = recall(question, messages)
    evidence = _evidence(question, parts, manifest)
    reserve = total-used-output
    report = {
        "schema": SCHEMA, "session_revision": session_revision,
        "model_digest": model_digest, "tokenizer_digest": tokenizer_digest,
        "question_sha256": _hash(question), "request_spans": parts,
        "suggested_specializations": roles, "complexity_heuristic": complexity,
        "suggested_effort": effort, "workflow": workflows,
        "memory": memory, "evidence": evidence,
        "budget": {"context_tokens": total, "input_estimate": used,
                   "output_reserved": output, "unreserved_units": reserve,
                   "omitted_history_messages": omitted,
                   "recommended_action": "review-context" if omitted else "review-plan"},
        "read_only": True, "generation_performed": False,
        "tool_execution_authorized": False, "memory_saved": False,
        "model_quality_measured": False, "prompt_modified": False,
    }
    report["preview_sha256"] = _canonical_hash(report)
    return report


def verify_preview(report):
    """Check content identity, not origin authenticity or future validity."""
    if type(report) is not dict or not _pin(report.get("preview_sha256")):
        return False
    return report["preview_sha256"] == _canonical_hash(
        {key: value for key, value in report.items() if key != "preview_sha256"})
