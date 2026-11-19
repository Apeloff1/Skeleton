/**
 * Academy Mastery Cockpit — 100 sliders across 10 categories.
 *
 *   • Each slider runs 0.0 (skip / suppress) → 3.0 (saturate).
 *   • 1.0 = neutral default.
 *   • Keys must be globally unique snake_case strings prefixed by category.
 */
import type { DnaTuple, DnaGroup } from './narrativeDnaData';

export const ACADEMY_DNA_GROUPS_DATA: DnaGroup[] = [
  // ── 1. Voice prosody (10) ────────────────────────────────────────
  { id: 'ac_voice', title: 'Voice prosody', icon: 'mic', color: '#a78bfa',
    hint: 'Fine grain control over delivered speech texture.',
    items: [
      ['ac_voice_rate_fine',  'Rate fine-tune',   'Adjust narration speed beyond global setting'],
      ['ac_voice_pitch_fine', 'Pitch fine-tune',  'Adjust narration pitch'],
      ['ac_voice_emphasis',   'Emphasis',         'Stress key words'],
      ['ac_voice_breath',     'Breath audibility','Allow soft breath sounds'],
      ['ac_voice_pauses',     'Pause length',     'Stretch or shrink natural pauses'],
      ['ac_voice_intonation', 'Intonation arc',   'Sentence-level pitch curve'],
      ['ac_voice_formal',     'Formality',        'Casual vs formal register'],
      ['ac_voice_energy',     'Energy',           'Calm vs excited delivery'],
      ['ac_voice_warmth',     'Warmth',           'Cold vs warm tone'],
      ['ac_voice_accent',     'Regional accent',  'Lean toward configured accent'],
    ] as DnaTuple[],
  },
  // ── 2. Pacing strategy (10) ──────────────────────────────────────
  { id: 'ac_pace', title: 'Pacing strategy', icon: 'speedometer', color: '#10b981',
    hint: 'How content flow accelerates or breathes.',
    items: [
      ['ac_pace_chapter',   'Chapter pace',       'Time between chapter transitions'],
      ['ac_pace_paragraph', 'Paragraph pace',     'Pause length between paragraphs'],
      ['ac_pace_sentence',  'Sentence pace',      'Pause between sentences'],
      ['ac_pace_beat',      'Beat pause',         'Mid-sentence dramatic beat'],
      ['ac_pace_character', 'Character per sec',  'Reading speed in chars/sec'],
      ['ac_pace_quote',     'Quote breath',       'Inhale before quoted lines'],
      ['ac_pace_dialog',    'Dialog pace',        'Speed-up during dialog'],
      ['ac_pace_narration', 'Narration pace',     'Speed of narrator passages'],
      ['ac_pace_suspense',  'Suspense stretch',   'Slow down on cliffhangers'],
      ['ac_pace_accel',     'Acceleration',       'Build-up speed in climaxes'],
    ] as DnaTuple[],
  },
  // ── 3. Code reading (10) ─────────────────────────────────────────
  { id: 'ac_code', title: 'Code reading', icon: 'code-slash', color: '#06b6d4',
    hint: 'How code blocks are pronounced and annotated.',
    items: [
      ['ac_code_verbose',     'Verbose code read',  'Read every char vs summarise'],
      ['ac_code_syntax',      'Syntax names',       'Say "open paren" vs skip'],
      ['ac_code_indent',      'Indent depth',       'Announce indent levels'],
      ['ac_code_comment',     'Comment read',       'Read inline comments aloud'],
      ['ac_code_langtag',     'Language tag',       'Announce language at block start'],
      ['ac_code_brackets',    'Brackets read',      'Pronounce brackets/braces'],
      ['ac_code_ident',       'Identifiers explained','Expand camelCase / snake_case'],
      ['ac_code_linenums',    'Line numbers',       'Announce line numbers'],
      ['ac_code_multiline',   'Multiline split',    'Break multi-line statements'],
      ['ac_code_focus',       'Focus mode',         'Highlight current line during read'],
    ] as DnaTuple[],
  },
  // ── 4. Audiobook UX (10) ─────────────────────────────────────────
  { id: 'ac_ux', title: 'Audiobook UX', icon: 'headset', color: '#ec4899',
    hint: 'Player-level conveniences.',
    items: [
      ['ac_ux_autoadv',  'Auto-advance',     'Auto play next chapter'],
      ['ac_ux_chime',    'Chapter chime',    'Audible cue between chapters'],
      ['ac_ux_bookmark', 'Bookmark depth',   'How many bookmarks to retain'],
      ['ac_ux_replay',   'Replay last',      'Replay last N seconds gesture'],
      ['ac_ux_sleep',    'Sleep-timer',      'Auto-pause after countdown'],
      ['ac_ux_phones',   'Headphone detect', 'Pause when unplugged'],
      ['ac_ux_duck',     'Audio ducking',    'Lower volume on notifications'],
      ['ac_ux_gesture',  'Gesture controls', 'Swipe seek / tap pause'],
      ['ac_ux_headtrack','Head-tracking',    'AirPods head-track support'],
      ['ac_ux_eq',       'EQ curve',         'Apply tuned equaliser'],
    ] as DnaTuple[],
  },
  // ── 5. Comprehension (10) ────────────────────────────────────────
  { id: 'ac_comp', title: 'Comprehension aids', icon: 'bulb', color: '#fbbf24',
    hint: 'Helpers that boost understanding.',
    items: [
      ['ac_comp_recap',    'Recap snippets',    'Auto-summarise after each section'],
      ['ac_comp_quiz',     'Quizlets',          'Insert mini-quizzes'],
      ['ac_comp_term',     'Term definitions',  'Define jargon inline'],
      ['ac_comp_glossary', 'Glossary push',     'Build per-book glossary'],
      ['ac_comp_mnemonic', 'Mnemonics',         'Add memory hooks'],
      ['ac_comp_example',  'Examples',          'Inline worked examples'],
      ['ac_comp_translate','Parallel translate','Show secondary-language text'],
      ['ac_comp_paraphr',  'Paraphrase',        'Restate complex passages simply'],
      ['ac_comp_xlink',    'Cross-links',       'Link to related sections'],
      ['ac_comp_footnote', 'Footnote read',     'Read footnotes aloud'],
    ] as DnaTuple[],
  },
  // ── 6. Display & legibility (10) ─────────────────────────────────
  { id: 'ac_disp', title: 'Display & legibility', icon: 'eye', color: '#3b82f6',
    hint: 'Visual rendering of reader text.',
    items: [
      ['ac_disp_fontsize',  'Font size',         'Body type size'],
      ['ac_disp_contrast',  'Contrast',          'Text vs background contrast'],
      ['ac_disp_lineheight','Line height',       'Vertical spacing'],
      ['ac_disp_letter',    'Letter spacing',    'Horizontal kern'],
      ['ac_disp_word',      'Word spacing',      'Between-word gap'],
      ['ac_disp_paragraph', 'Paragraph spacing', 'Gap between paragraphs'],
      ['ac_disp_syntax',    'Syntax highlight',  'Intensity of code colours'],
      ['ac_disp_focusdim',  'Focus dim',         'Dim non-focus paragraphs'],
      ['ac_disp_halo',      'Hover halo',        'Subtle highlight on hover'],
      ['ac_disp_colorshift','Colour shift',      'Warm vs cool palette bias'],
    ] as DnaTuple[],
  },
  // ── 7. Difficulty (10) ───────────────────────────────────────────
  { id: 'ac_diff', title: 'Difficulty tuning', icon: 'trending-up', color: '#f97316',
    hint: 'How dense / advanced the rendered material is.',
    items: [
      ['ac_diff_vocab',    'Vocabulary level',  'Simple → academic'],
      ['ac_diff_syntax',   'Syntax complexity', 'Short sentences vs nested clauses'],
      ['ac_diff_length',   'Sentence length',   'Average words per sentence'],
      ['ac_diff_idiom',    'Idioms allowed',    'Frequency of idiomatic usage'],
      ['ac_diff_jargon',   'Technical jargon',  'Frequency of domain terms'],
      ['ac_diff_abstract', 'Abstraction depth', 'Concrete examples vs abstract laws'],
      ['ac_diff_math',     'Math notation',     'Inline math density'],
      ['ac_diff_proof',    'Formal proofs',     'Include formal proof passages'],
      ['ac_diff_code',     'Code density',      'Lines of code per page'],
      ['ac_diff_latency',  'Response latency',  'Patience vs urgency in pace'],
    ] as DnaTuple[],
  },
  // ── 8. Engagement loops (10) ─────────────────────────────────────
  { id: 'ac_eng', title: 'Engagement loops', icon: 'sparkles', color: '#22d3ee',
    hint: 'Gamification & retention cadence.',
    items: [
      ['ac_eng_xp',         'XP curve',         'Steepness of XP gain'],
      ['ac_eng_level',      'Level cadence',    'How often levels rise'],
      ['ac_eng_badge',      'Badge frequency',  'Rare → common badge drops'],
      ['ac_eng_streak',     'Streak weight',    'How heavily streaks matter'],
      ['ac_eng_celebrate',  'Celebration',      'Intensity of milestone fanfare'],
      ['ac_eng_ambient',    'Ambient music',    'Background score volume'],
      ['ac_eng_weekly',     'Weekly recap',     'Auto weekly progress summary'],
      ['ac_eng_daily',      'Daily push',       'Notification cadence'],
      ['ac_eng_drop',       'Surprise drops',   'Random bonus content frequency'],
      ['ac_eng_cohort',     'Cohort spotlight', 'Highlight peers achievements'],
    ] as DnaTuple[],
  },
  // ── 9. Adaptive review (10) ──────────────────────────────────────
  { id: 'ac_rev', title: 'Adaptive review', icon: 'refresh', color: '#10b981',
    hint: 'How the system reinforces weak spots.',
    items: [
      ['ac_rev_sr',        'Spaced repetition', 'SRS scheduling aggressiveness'],
      ['ac_rev_errfocus',  'Error focus',       'Re-quiz on wrong answers'],
      ['ac_rev_drill',     'Weak-spot drill',   'Auto-drill weak topics'],
      ['ac_rev_dwell',     'Dwell-time bias',   'Re-explain when slow'],
      ['ac_rev_reexplain', 'Re-explain trigger','Auto re-explain on misses'],
      ['ac_rev_hint',      'Hint frequency',    'How readily hints appear'],
      ['ac_rev_scaffold',  'Scaffolding',       'Leading vs full-walk-through'],
      ['ac_rev_mastery',   'Mastery threshold', '% to call a topic mastered'],
      ['ac_rev_retry',     'Retry cadence',     'When to revisit a topic'],
      ['ac_rev_forget',    'Forgetting curve',  'Spacing curve aggressiveness'],
    ] as DnaTuple[],
  },
  // ── 10. Accessibility (10) ───────────────────────────────────────
  { id: 'ac_a11y', title: 'Accessibility', icon: 'accessibility', color: '#ef4444',
    hint: 'Inclusive defaults.',
    items: [
      ['ac_a11y_contrast', 'High contrast',     'Lock high-contrast palette'],
      ['ac_a11y_dyslexia', 'Dyslexia font',     'Use OpenDyslexic-style fonts'],
      ['ac_a11y_motion',   'Motion reduce',     'Suppress non-essential animation'],
      ['ac_a11y_srecho',   'Screen-reader echo','Mirror UI labels to AT layer'],
      ['ac_a11y_subtitle', 'Subtitle sync',     'Auto-sync captions'],
      ['ac_a11y_audiodesc','Audio descriptions','Describe imagery aloud'],
      ['ac_a11y_haptic',   'Haptic cues',       'Tap feedback on key events'],
      ['ac_a11y_slowdown', 'Slow-down hotkey',  'Single-tap speed reducer'],
      ['ac_a11y_keyboard', 'Keyboard nav',      'Full keyboard accessibility'],
      ['ac_a11y_magnify',  'Magnifier',         'In-app magnifier strength'],
    ] as DnaTuple[],
  },
];

export const ACADEMY_DNA_KEYS: readonly string[] =
  ACADEMY_DNA_GROUPS_DATA.flatMap(g => g.items.map(([k]) => k));

export const ACADEMY_DNA_TOTAL = ACADEMY_DNA_KEYS.length; // 100
