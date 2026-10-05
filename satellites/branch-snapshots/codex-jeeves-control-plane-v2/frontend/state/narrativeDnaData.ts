/**
 * Narrative DNA Cockpit — 500 sliders across 30 categories.
 *
 * Each slider runs 0.0 (skip / absent) → 3.0 (saturate).
 * 1.0 = default, neutral influence.
 *
 * Edit ONLY this file to add/remove sliders. Keys must be globally
 * unique kebab-snake-case strings (prefixed by category).
 *
 * Format: [key, label, hint] tuples for compactness.
 */

export type DnaTuple = readonly [string, string, string];

export interface DnaGroup {
  id: string;
  title: string;
  icon: string;
  color: string;
  hint: string;
  items: DnaTuple[];
}

export const NARRATIVE_DNA_GROUPS_DATA: DnaGroup[] = [
  // ── 1. Archetypes (30) ──────────────────────────────────────────────
  {
    id: 'archetypes', title: 'Archetypes', icon: 'people', color: '#8B5CF6',
    hint: 'Joseph-Campbell-style narrative roles. Push to 0 to skip, 3× to saturate.',
    items: [
      ['arc_hero', 'Hero', 'Driver of the journey, voice of the player'],
      ['arc_mentor', 'Mentor', 'Imparts wisdom and gifts of guidance'],
      ['arc_trickster', 'Trickster', 'Disrupts plans, comic relief and chaos'],
      ['arc_shadow', 'Shadow', 'Dark mirror of the hero, antagonist'],
      ['arc_ally', 'Ally', 'Loyal companion who completes the team'],
      ['arc_threshold_guardian', 'Threshold Guardian', 'Tests the hero before they cross'],
      ['arc_herald', 'Herald', 'Announces the call to adventure'],
      ['arc_shapeshifter', 'Shapeshifter', 'Allegiance unclear; identity fluid'],
      ['arc_lover', 'Lover', 'Romantic / emotional anchor'],
      ['arc_outlaw', 'Outlaw', 'Rebels against the system with style'],
      ['arc_ruler', 'Ruler', 'Authority figure shaping the world order'],
      ['arc_sage', 'Sage', 'Pursuer of truth and understanding'],
      ['arc_caregiver', 'Caregiver', 'Protects and nurtures others'],
      ['arc_explorer', 'Explorer', 'Seeker of the new horizon'],
      ['arc_creator', 'Creator', 'Builder, artisan, world-shaper'],
      ['arc_innocent', 'Innocent', 'Pure soul, untouched by cynicism'],
      ['arc_jester', 'Jester', 'Mirth that punctures pretension'],
      ['arc_magician', 'Magician', 'Transforms reality through will'],
      ['arc_warrior', 'Warrior', 'Disciplined combatant of conviction'],
      ['arc_rebel', 'Rebel', 'Burns the old order down'],
      ['arc_orphan', 'Orphan', 'Yearning to belong somewhere'],
      ['arc_destroyer', 'Destroyer', 'Necessary unmaker of the rotten'],
      ['arc_paragon', 'Paragon', 'Embodies the ideal virtues'],
      ['arc_byronic', 'Byronic Hero', 'Brooding, charismatic, flawed'],
      ['arc_anti_villain', 'Anti-Villain', 'Sympathetic foe with noble motive'],
      ['arc_chosen_one', 'Chosen One', 'Marked by prophecy for greatness'],
      ['arc_reluctant_hero', 'Reluctant Hero', 'Drafted unwillingly into destiny'],
      ['arc_fallen_hero', 'Fallen Hero', 'Once-great figure now broken'],
      ['arc_dark_lord', 'Dark Lord', 'Sovereign of evil and dread'],
      ['arc_god_in_disguise', 'God in Disguise', 'Divine power walks among mortals'],
    ],
  },

  // ── 2. Xenotypes (25) ───────────────────────────────────────────────
  {
    id: 'xenotypes', title: 'Xenotypes', icon: 'planet', color: '#06B6D4',
    hint: 'Non-human creature templates. Mix to seed unique alien casts.',
    items: [
      ['xeno_humanoid', 'Humanoid', 'Bipedal, recognisably human-derived'],
      ['xeno_synthetic', 'Synthetic', 'Machines, AIs, constructs'],
      ['xeno_hivemind', 'Hivemind', 'Collective intelligence, swarm'],
      ['xeno_reptilian', 'Reptilian', 'Scaled, cold-blooded, sometimes regal'],
      ['xeno_insectoid', 'Insectoid', 'Chitin, mandibles, multi-limbed'],
      ['xeno_avian', 'Avian', 'Winged, beaked, sky-faring'],
      ['xeno_aquatic', 'Aquatic', 'Gilled, finned, deep-sea / amphibious'],
      ['xeno_plant', 'Plant-based', 'Vegetal, fungal, root-networked'],
      ['xeno_energy', 'Energy-being', 'Pure plasma / radiation / thought'],
      ['xeno_spectral', 'Spectral', 'Incorporeal, undead, dream-shade'],
      ['xeno_crystalline', 'Crystalline', 'Silicate lattice; refracts light'],
      ['xeno_gaseous', 'Gaseous', 'Cloud-form, drifts on currents'],
      ['xeno_fungal', 'Fungal', 'Mycelial network, spore-borne'],
      ['xeno_silicon', 'Silicon-based', 'Slow metabolism, deep heat tolerant'],
      ['xeno_eldritch', 'Eldritch', 'Geometry-breaking, sanity-eating'],
      ['xeno_celestial', 'Celestial', 'Star-spawned, radiant authority'],
      ['xeno_chthonic', 'Chthonic', 'Underworld-born, earth-shaper'],
      ['xeno_ursine', 'Ursine', 'Bear-derived, towering, gentle wrath'],
      ['xeno_feline', 'Feline', 'Sleek, predatory, prideful'],
      ['xeno_canine', 'Canine', 'Pack-driven, loyal, scent-keen'],
      ['xeno_arachnid', 'Arachnid', 'Many-legged, web-builder, patient'],
      ['xeno_cephalopod', 'Cephalopod', 'Tentacled, chromatic, brilliant'],
      ['xeno_lithic', 'Lithic', 'Stone-bodied, slow-thinking, mountainous'],
      ['xeno_amorphous', 'Amorphous', 'Shape-less, fluid, devouring'],
      ['xeno_voidborn', 'Voidborn', 'Hails from the dark between stars'],
    ],
  },

  // ── 3. Character Types (25) ─────────────────────────────────────────
  {
    id: 'character_types', title: 'Character Types', icon: 'person', color: '#F59E0B',
    hint: 'Functional cast roles — independent of species or arc.',
    items: [
      ['char_protagonist', 'Protagonist', 'Central viewpoint character'],
      ['char_antagonist', 'Antagonist', 'Primary opposing force'],
      ['char_foil', 'Foil', 'Contrasts to highlight the protagonist'],
      ['char_mentor', 'Mentor', 'Wise guide; overlaps with archetype'],
      ['char_sidekick', 'Sidekick', 'Loyal helper of lower stature'],
      ['char_trickster', 'Trickster', 'Chaos comedian, overlaps with arc'],
      ['char_antihero', 'Anti-hero', 'Morally grey lead'],
      ['char_tragic', 'Tragic Hero', 'Doomed by a fatal flaw'],
      ['char_everyman', 'Everyman', 'Relatable, ordinary entry point'],
      ['char_round', 'Round / Complex', 'Multi-faceted, contradictory'],
      ['char_stock', 'Stock Character', 'Familiar archetype, low surprise'],
      ['char_archetypal', 'Archetypal', 'Distilled essence of a role'],
      ['char_dynamic', 'Dynamic', 'Changes meaningfully across the arc'],
      ['char_static', 'Static', 'Stable anchor amid change'],
      ['char_confidant', 'Confidant', 'Receives secrets, gives counsel'],
      ['char_love_interest', 'Love Interest', 'Romantic gravity well'],
      ['char_rival', 'Rival', 'Equal pushing the protagonist'],
      ['char_henchman', 'Henchman', 'Mid-rank antagonist enforcer'],
      ['char_bystander', 'Bystander', 'Caught in events, agency limited'],
      ['char_innocent_witness', 'Innocent Witness', 'Sees, names, fears the truth'],
      ['char_narrator', 'Narrator', 'Voices the story, may be unreliable'],
      ['char_femme_fatale', 'Femme/Homme Fatale', 'Beautiful danger of mixed motive'],
      ['char_chosen_outsider', 'Chosen Outsider', 'Stranger destined to belong'],
      ['char_double_agent', 'Double Agent', 'Plays both sides; loyalty unclear'],
      ['char_redeemed', 'Redeemed Villain', 'Crosses back to the light'],
    ],
  },

  // ── 4. Tone & Theme (32) ────────────────────────────────────────────
  {
    id: 'tone_theme', title: 'Tone & Theme', icon: 'color-filter', color: '#EC4899',
    hint: 'Overall narrative flavour. Pile up to push the build hard in one direction.',
    items: [
      ['tone_grimdark', 'Grim-darkness', 'Bleak, cynical, hope-starved'],
      ['tone_whimsy', 'Whimsy', 'Playful, fairy-tale lightness'],
      ['tone_hope', 'Hope', 'Optimistic arcs, redemption likely'],
      ['tone_melancholy', 'Melancholy', 'Wistful, contemplative sadness'],
      ['tone_tension', 'Tension', 'Suspense, dread, edge-of-seat pacing'],
      ['tone_romance', 'Romance', 'Love at the centre of the story'],
      ['tone_mystery', 'Mystery', 'Investigation, secrets, red herrings'],
      ['tone_adventure', 'Adventure', 'Exploration, wonder, journey'],
      ['tone_horror', 'Horror', 'Fear, body horror, cosmic dread'],
      ['tone_comedy', 'Comedy', 'Jokes, gags, light banter'],
      ['tone_drama', 'Drama', 'Interpersonal stakes, emotional heft'],
      ['tone_political', 'Political', 'Power, factions, statecraft'],
      ['tone_philosophical', 'Philosophical', 'Big questions, meaning, ethics'],
      ['tone_satirical', 'Satirical', 'Sharp commentary disguised as story'],
      ['tone_absurdist', 'Absurdist', 'Meaningless universe, comic logic'],
      ['tone_ironic', 'Ironic', 'Said one way, meant another'],
      ['tone_nostalgic', 'Nostalgic', 'Bittersweet warmth for what was'],
      ['tone_apocalyptic', 'Apocalyptic', 'End-times stakes, civilisation falling'],
      ['tone_dreamy', 'Dreamy', 'Soft, hazy, half-remembered'],
      ['tone_surreal', 'Surreal', 'Logic dissolves at the edges'],
      ['tone_cynical', 'Cynical', 'Trust nothing, expect betrayal'],
      ['tone_wholesome', 'Wholesome', 'Kindness rewarded, warmth wins'],
      ['tone_visceral', 'Visceral', 'Body-aware, sweaty, bleeding'],
      ['tone_meditative', 'Meditative', 'Stillness, breath, quiet attention'],
      ['tone_chaotic', 'Chaotic', 'No two scenes agree on tone'],
      ['tone_solemn', 'Solemn', 'Ceremonial, weighty, measured'],
      ['tone_camp', 'Camp', 'Knowingly excessive, fabulously absurd'],
      ['tone_noir', 'Noir', 'Smoke, rain, doomed protagonist'],
      ['tone_gothic', 'Gothic', 'Decay, dread, transgressive love'],
      ['tone_pastoral', 'Pastoral', 'Idyllic countryside, slow living'],
      ['tone_epic', 'Epic', 'Vast scale, civilisations at stake'],
      ['tone_intimate', 'Intimate', 'Tight focus on one heart'],
    ],
  },

  // ── 5. Genre DNA (32) ───────────────────────────────────────────────
  {
    id: 'genre_dna', title: 'Genre DNA', icon: 'film', color: '#10B981',
    hint: 'Genre lineage. Mix freely to mutate, isolate to purify.',
    items: [
      ['gen_cyberpunk', 'Cyberpunk', 'Neon, megacorps, body mods'],
      ['gen_solarpunk', 'Solarpunk', 'Green tech, communal optimism'],
      ['gen_steampunk', 'Steampunk', 'Brass, gears, Victorian futurism'],
      ['gen_dieselpunk', 'Dieselpunk', 'Greasy 1930s war-machine aesthetic'],
      ['gen_atompunk', 'Atompunk', 'Mid-century atomic optimism'],
      ['gen_biopunk', 'Biopunk', 'Wet tech, gene splicing, bodily horror'],
      ['gen_clockpunk', 'Clockpunk', 'Renaissance automata, fine clockwork'],
      ['gen_mythpunk', 'Mythpunk', 'Folklore remixed with modernity'],
      ['gen_silkpunk', 'Silkpunk', 'East-Asian bamboo-and-silk futurism'],
      ['gen_space_opera', 'Space Opera', 'Galaxy-spanning melodrama'],
      ['gen_hard_sf', 'Hard SF', 'Rigorous physics, rivets count'],
      ['gen_soft_sf', 'Soft SF', 'Sociology over physics'],
      ['gen_high_fantasy', 'High Fantasy', 'Secondary world, magic abundant'],
      ['gen_low_fantasy', 'Low Fantasy', 'Magic rare, sneaks into our world'],
      ['gen_urban_fantasy', 'Urban Fantasy', 'Magic hidden in modern cities'],
      ['gen_grimdark_fantasy', 'Grimdark Fantasy', 'Brutal, cynical sword-and-sorcery'],
      ['gen_sword_sorcery', 'Sword & Sorcery', 'Episodic hero, pulpy stakes'],
      ['gen_post_apoc', 'Post-Apocalyptic', 'After the world ended'],
      ['gen_dystopian', 'Dystopian', 'Society as cage'],
      ['gen_utopian', 'Utopian', 'Society as solved problem'],
      ['gen_dark_academia', 'Dark Academia', 'Tweed, secrets, knowledge that kills'],
      ['gen_cosmic_horror', 'Cosmic Horror', 'Indifferent universe, fragile minds'],
      ['gen_gothic_horror', 'Gothic Horror', 'Crumbling estates, family curses'],
      ['gen_slasher', 'Slasher', 'Stalker, victims, final survivor'],
      ['gen_psych_horror', 'Psychological Horror', 'Dread from within the mind'],
      ['gen_western', 'Western', 'Frontier, six-guns, dust and code'],
      ['gen_wuxia', 'Wuxia', 'Martial heroes, jianghu code'],
      ['gen_xianxia', 'Xianxia', 'Cultivation toward immortality'],
      ['gen_isekai', 'Isekai', 'Transported to another world'],
      ['gen_litrpg', 'LitRPG', 'Levels, stats, system text in-fiction'],
      ['gen_mecha', 'Mecha', 'Piloted giant machines'],
      ['gen_kaiju', 'Kaiju', 'Skyscraper-scale beasts ravage cities'],
    ],
  },

  // ── 6. Setting / Era (24) ───────────────────────────────────────────
  {
    id: 'era', title: 'Setting / Era', icon: 'hourglass', color: '#0EA5E9',
    hint: 'Historical / chronological backbone. Stack for anachronism.',
    items: [
      ['era_paleolithic', 'Paleolithic', 'Stone tools, hunter-gatherer bands'],
      ['era_neolithic', 'Neolithic', 'Early agriculture, first villages'],
      ['era_bronze', 'Bronze Age', 'Chariots, ziggurats, early empires'],
      ['era_iron', 'Iron Age', 'Iron weapons, expanding kingdoms'],
      ['era_classical', 'Classical Antiquity', 'Greco-Roman world, philosophy born'],
      ['era_dark_ages', 'Dark Ages', 'Post-imperial collapse, monasteries'],
      ['era_medieval', 'Medieval', 'Feudal lords, cathedrals, plague'],
      ['era_renaissance', 'Renaissance', 'Revival of art and humanism'],
      ['era_age_of_sail', 'Age of Sail', 'Wooden ships, blue-water empires'],
      ['era_colonial', 'Colonial', 'Empire abroad, friction at home'],
      ['era_industrial', 'Industrial', 'Steam, factories, smoke cities'],
      ['era_victorian', 'Victorian', 'Empire at zenith, propriety + grime'],
      ['era_edwardian', 'Edwardian', 'Last golden afternoon before war'],
      ['era_belle_epoque', 'Belle Époque', 'Optimistic continental Europe'],
      ['era_great_war', 'Great War', 'Trenches, modernity born violently'],
      ['era_interwar', 'Interwar', 'Jazz, depression, ideology rising'],
      ['era_atomic', 'Atomic Age', 'Mushroom cloud over the picket fence'],
      ['era_space_age', 'Space Age', 'Sputnik, Apollo, optimism toward stars'],
      ['era_information', 'Information Age', 'PCs, web, surveillance, attention'],
      ['era_near_future', 'Near Future', 'Five minutes ahead of today'],
      ['era_far_future', 'Far Future', 'Centuries on, humanity transformed'],
      ['era_post_singularity', 'Post-Singularity', 'Intelligence explosion fallout'],
      ['era_deep_time', 'Deep Time', 'Millions of years, geologic stakes'],
      ['era_timeless', 'Timeless / Mythic', 'Outside chronology entirely'],
    ],
  },

  // ── 7. Conflict Types (18) ──────────────────────────────────────────
  {
    id: 'conflict', title: 'Conflict Types', icon: 'flash', color: '#EF4444',
    hint: 'The central friction(s). Layer multiple for thematic density.',
    items: [
      ['conf_man_vs_man', 'Person vs. Person', 'Direct interpersonal opposition'],
      ['conf_man_vs_nature', 'Person vs. Nature', 'The world itself is the obstacle'],
      ['conf_man_vs_self', 'Person vs. Self', 'Internal war is the story'],
      ['conf_man_vs_society', 'Person vs. Society', 'The rules of the world push back'],
      ['conf_man_vs_tech', 'Person vs. Technology', 'Created tools turn or trap'],
      ['conf_man_vs_god', 'Person vs. God', 'Cosmic authority is the adversary'],
      ['conf_man_vs_fate', 'Person vs. Fate', 'Prophecy / determinism resists choice'],
      ['conf_man_vs_supernatural', 'Person vs. Supernatural', 'Magic / spirit is the threat'],
      ['conf_man_vs_machine', 'Person vs. Machine', 'AI or autonomous weapons rise'],
      ['conf_man_vs_alien', 'Person vs. Alien', 'First contact gone wrong'],
      ['conf_group_vs_group', 'Group vs. Group', 'Factions, armies, tribes clash'],
      ['conf_civ_vs_wild', 'Civilisation vs. Wild', 'Frontier; what counts as home'],
      ['conf_order_vs_chaos', 'Order vs. Chaos', 'Law and entropy fight for shape'],
      ['conf_freedom_vs_security', 'Freedom vs. Security', 'What will you trade for safety'],
      ['conf_tradition_vs_progress', 'Tradition vs. Progress', 'The past insists, the future demands'],
      ['conf_known_vs_unknown', 'Known vs. Unknown', 'Mystery is the principal antagonist'],
      ['conf_individual_vs_collective', 'Individual vs. Collective', 'Self or the many'],
      ['conf_creation_vs_destruction', 'Creation vs. Destruction', 'To build or to unmake'],
    ],
  },

  // ── 8. Plot Devices (24) ────────────────────────────────────────────
  {
    id: 'plot_devices', title: 'Plot Devices', icon: 'sparkles', color: '#F97316',
    hint: 'Toolbox of structural moves. Use sparingly or weaponise heavily.',
    items: [
      ['plot_mcguffin', 'MacGuffin', 'Object everyone wants, plot fuel'],
      ['plot_red_herring', 'Red Herring', 'False lead to mislead the audience'],
      ['plot_chekhov_gun', 'Chekhov’s Gun', 'Visible early, fires later'],
      ['plot_deus_ex', 'Deus ex Machina', 'External rescue from impossible jam'],
      ['plot_in_medias_res', 'In Medias Res', 'Start mid-action'],
      ['plot_flashback', 'Flashback', 'Past illuminates present'],
      ['plot_flash_forward', 'Flash-forward', 'Glimpse of what is coming'],
      ['plot_unreliable_narrator', 'Unreliable Narrator', 'Voice you can’t fully trust'],
      ['plot_frame_story', 'Frame Story', 'Tale within a telling'],
      ['plot_nested_story', 'Nested Story', 'Stories inside stories inside stories'],
      ['plot_foreshadowing', 'Foreshadowing', 'Plant seeds for later harvest'],
      ['plot_dramatic_irony', 'Dramatic Irony', 'Audience knows what character doesn’t'],
      ['plot_twist', 'Plot Twist', 'Sudden reframe of the truth'],
      ['plot_double_twist', 'Double Twist', 'Twist on the twist'],
      ['plot_prophecy', 'Prophecy', 'Foretold outcomes loom over choices'],
      ['plot_amnesia', 'Amnesia', 'Identity reconstructed from clues'],
      ['plot_doppelganger', 'Doppelgänger', 'Double of the hero appears'],
      ['plot_time_loop', 'Time Loop', 'Same period replays until learned'],
      ['plot_parallel_worlds', 'Parallel Worlds', 'Other versions intersect'],
      ['plot_hidden_identity', 'Hidden Identity', 'True self revealed at climax'],
      ['plot_quest', 'Quest', 'Long-form goal organising the journey'],
      ['plot_betrayal', 'Betrayal', 'Trusted ally turns'],
      ['plot_revenge', 'Revenge', 'Wrong drives the engine'],
      ['plot_redemption', 'Redemption', 'Atonement arc reframes a life'],
    ],
  },

  // ── 9. Narrative Pacing (12) ────────────────────────────────────────
  {
    id: 'pacing', title: 'Narrative Pacing', icon: 'speedometer', color: '#A855F7',
    hint: 'Rate at which events unfold. Mix for textured rhythm.',
    items: [
      ['pace_brisk', 'Brisk', 'Constant forward motion'],
      ['pace_languid', 'Languid', 'Lingering on mood and detail'],
      ['pace_breakneck', 'Breakneck', 'No breath, every page kinetic'],
      ['pace_meditative', 'Meditative', 'Stillness as substance'],
      ['pace_episodic', 'Episodic', 'Self-contained arcs string together'],
      ['pace_serial', 'Serial', 'Long ongoing arc, cliffhangers'],
      ['pace_slow_burn', 'Slow Burn', 'Heat builds gradually to detonation'],
      ['pace_layered', 'Layered', 'Multiple timelines and threads'],
      ['pace_rhythmic_pulse', 'Rhythmic Pulse', 'Beats fall on regular cadence'],
      ['pace_crescendo', 'Crescendo', 'Steadily rising intensity'],
      ['pace_decrescendo', 'Decrescendo', 'Loud start, quieter end'],
      ['pace_punctuated', 'Punctuated Equilibrium', 'Long calm, sudden upheaval'],
    ],
  },

  // ── 10. World-Building Density (17) ────────────────────────────────
  {
    id: 'world_density', title: 'World-Building Density', icon: 'earth', color: '#22C55E',
    hint: 'How richly the world is described and how it lives off-screen.',
    items: [
      ['world_lore_dense', 'Lore-Dense', 'Footnotes, appendices, glossaries'],
      ['world_lore_sparse', 'Lore-Sparse', 'Just enough to ground the scene'],
      ['world_living_history', 'Living History', 'Past actively shapes today'],
      ['world_static_history', 'Static History', 'Old world is mostly inert backdrop'],
      ['world_explicit_rules', 'Explicit Rules', 'Magic / physics stated plainly'],
      ['world_implicit_rules', 'Implicit Rules', 'Discover the rules by friction'],
      ['world_cartographic', 'Cartographic', 'Maps matter, geography is a character'],
      ['world_psychological', 'Psychological', 'Inner lives of cultures sketched'],
      ['world_economic', 'Economic', 'Trade, currency, supply chains shown'],
      ['world_ecological', 'Ecological', 'Biomes, food webs, weather felt'],
      ['world_linguistic', 'Linguistic', 'Languages, dialects, etymologies'],
      ['world_culinary', 'Culinary', 'What people eat, how, why'],
      ['world_religious', 'Religious', 'Faiths, rites, schisms textured'],
      ['world_legal', 'Legal', 'Law as living, contested system'],
      ['world_architectural', 'Architectural', 'Buildings tell stories'],
      ['world_meteorological', 'Meteorological', 'Weather actively narrates'],
      ['world_metaphysical', 'Metaphysical', 'Cosmology is part of plot'],
    ],
  },

  // ── 11. Magic Systems (18) ──────────────────────────────────────────
  {
    id: 'magic', title: 'Magic Systems', icon: 'flame', color: '#D946EF',
    hint: 'Sanderson-style hard/soft taxonomy plus thematic flavours.',
    items: [
      ['mag_hard', 'Hard Magic', 'Strict rules, predictable costs'],
      ['mag_soft', 'Soft Magic', 'Mysterious, wonder over rules'],
      ['mag_elemental', 'Elemental', 'Fire, water, earth, air, beyond'],
      ['mag_runic', 'Runic', 'Inscribed glyphs power effects'],
      ['mag_blood', 'Blood Magic', 'Power at literal cost of the body'],
      ['mag_soul', 'Soul Magic', 'Trades and breaks the inner spark'],
      ['mag_name', 'Name Magic', 'True names compel and shape'],
      ['mag_pact', 'Pact Magic', 'Power borrowed by binding agreement'],
      ['mag_ritual', 'Ritual Magic', 'Time + ingredients + procedure'],
      ['mag_chaos', 'Chaos Magic', 'Probability-bending, risky'],
      ['mag_color', 'Colour Magic', 'Spectrum-coded disciplines'],
      ['mag_song', 'Song Magic', 'Sung incantations, bardic'],
      ['mag_motion', 'Motion Magic', 'Gesture + footwork → effect'],
      ['mag_seasonal', 'Seasonal Magic', 'Power waxes / wanes with year'],
      ['mag_planar', 'Planar Magic', 'Cross-dimensional travel and pull'],
      ['mag_alchemical', 'Alchemical', 'Transmutation, elixirs, panaceas'],
      ['mag_psionic', 'Psionic', 'Mind-power, telepathy, kinesis'],
      ['mag_divine', 'Divine', 'Borrowed authority of a deity'],
    ],
  },

  // ── 12. Tech Levels (12) ────────────────────────────────────────────
  {
    id: 'tech', title: 'Tech Levels', icon: 'hardware-chip', color: '#3B82F6',
    hint: 'Civilisational tech ceiling. Layer for anachronistic frontier vibes.',
    items: [
      ['tech_stone', 'Stone Age', 'Knapped flint, fire, fibre'],
      ['tech_bronze', 'Bronze', 'Alloyed weapons, written record'],
      ['tech_iron', 'Iron', 'Hardened tools, expanding empires'],
      ['tech_steam', 'Steam', 'Pressure does the work'],
      ['tech_clockwork', 'Clockwork', 'Precision mechanism rules'],
      ['tech_electric', 'Electric', 'Wired light, telegraph, radio'],
      ['tech_nuclear', 'Nuclear', 'Atomic energy reshapes geopolitics'],
      ['tech_information', 'Information', 'Networks, code, attention markets'],
      ['tech_nano', 'Nanotech', 'Atom-precise engineering'],
      ['tech_bio', 'Biotech', 'Engineered life, designer cells'],
      ['tech_singularity', 'Singularity', 'Self-improving intelligence loose'],
      ['tech_post_scarcity', 'Post-Scarcity', 'Replicators end want'],
    ],
  },

  // ── 13. Economy & Politics (18) ────────────────────────────────────
  {
    id: 'econ_pol', title: 'Economy & Politics', icon: 'business', color: '#84CC16',
    hint: 'Material base + power structure shape every story choice.',
    items: [
      ['econ_barter', 'Barter Economy', 'Direct exchange, no money'],
      ['econ_feudal', 'Feudal', 'Land for loyalty, peasants tied'],
      ['econ_mercantile', 'Mercantile', 'Long-distance trade rules'],
      ['econ_capitalist', 'Capitalist', 'Markets, capital, accumulation'],
      ['econ_socialist', 'Socialist', 'Collective ownership of means'],
      ['econ_post_scarcity_econ', 'Post-Scarcity Econ', 'Abundance changes incentive'],
      ['econ_black_market', 'Black Market', 'Underground commerce thrives'],
      ['econ_gift', 'Gift Economy', 'Status flows through generosity'],
      ['econ_corporate', 'Corporate State', 'Megacorps eclipse governments'],
      ['econ_resource_scarce', 'Resource Scarcity', 'Water, fuel, food drive the plot'],
      ['pol_anarchic', 'Anarchic', 'No central authority'],
      ['pol_tribal', 'Tribal', 'Kinship determines law'],
      ['pol_theocratic', 'Theocratic', 'Priests are the state'],
      ['pol_monarchic', 'Monarchic', 'A bloodline rules'],
      ['pol_oligarchic', 'Oligarchic', 'Few wealthy houses run things'],
      ['pol_democratic', 'Democratic', 'Many voices, slow consensus'],
      ['pol_technocratic', 'Technocratic', 'Experts govern by metric'],
      ['pol_totalitarian', 'Totalitarian', 'Total control of all life'],
    ],
  },

  // ── 14. Faction Templates (18) ─────────────────────────────────────
  {
    id: 'factions', title: 'Faction Templates', icon: 'shield-half', color: '#FBBF24',
    hint: 'Pre-baked organisational moulds. Stack to multiply political density.',
    items: [
      ['fact_empire', 'Empire', 'Hegemonic state, taxation and legions'],
      ['fact_rebellion', 'Rebellion', 'Loose alliance against power'],
      ['fact_guild', 'Guild', 'Trade monopoly, sworn craft'],
      ['fact_cult', 'Cult', 'Charismatic leader, secret rites'],
      ['fact_megacorp', 'Megacorp', 'Corporation as sovereign'],
      ['fact_syndicate', 'Syndicate', 'Organised crime federation'],
      ['fact_clan', 'Clan', 'Extended family of loyalty'],
      ['fact_order', 'Knightly Order', 'Sworn brotherhood with code'],
      ['fact_secret_society', 'Secret Society', 'Hidden hands tug history'],
      ['fact_priesthood', 'Priesthood', 'Keepers of sacred knowledge'],
      ['fact_academy', 'Academy', 'Walled learning, jealous archives'],
      ['fact_nomads', 'Nomads', 'No fixed home; trade carries identity'],
      ['fact_pirates', 'Pirates', 'Lawless seafarers / spacers'],
      ['fact_mercenaries', 'Mercenaries', 'Loyalty to the contract only'],
      ['fact_dynasty', 'Dynasty', 'Family that has ruled for ages'],
      ['fact_collective', 'Collective', 'Voluntary co-operative cell'],
      ['fact_underground', 'Underground', 'Buried network of dissidents'],
      ['fact_remnant', 'Remnant', 'Last survivors of a fallen power'],
    ],
  },

  // ── 15. Romance Subtypes (12) ──────────────────────────────────────
  {
    id: 'romance', title: 'Romance Subtypes', icon: 'heart', color: '#F43F5E',
    hint: 'Optional romantic threads — saturate, abstain, or pick a flavour.',
    items: [
      ['rom_enemies_to_lovers', 'Enemies to Lovers', 'Antipathy melts to passion'],
      ['rom_friends_to_lovers', 'Friends to Lovers', 'Years of friendship cross a line'],
      ['rom_forbidden', 'Forbidden Love', 'Social wall must be broken'],
      ['rom_slow_burn', 'Slow Burn', 'Tension accumulates exquisitely'],
      ['rom_triangle', 'Love Triangle', 'Three vertices in tension'],
      ['rom_arranged', 'Arranged Marriage', 'Strangers thrown together'],
      ['rom_second_chance', 'Second Chance', 'Old flame rekindles'],
      ['rom_unrequited', 'Unrequited', 'Love one-sided'],
      ['rom_star_crossed', 'Star-Crossed', 'Fate stands between them'],
      ['rom_convenience', 'Marriage of Convenience', 'Strategic pact becomes real'],
      ['rom_one_sided', 'One-Sided Devotion', 'Only one carries the torch'],
      ['rom_polyamory', 'Polyamory', 'Multiple bonds woven openly'],
    ],
  },

  // ── 16. Climax Style (10) ──────────────────────────────────────────
  {
    id: 'climax', title: 'Climax Style', icon: 'flag', color: '#DC2626',
    hint: 'Shape of the apex moment. Pick one or contrast two.',
    items: [
      ['clim_grand_battle', 'Grand Battle', 'Armies clash on open ground'],
      ['clim_duel', 'Duel', 'One-to-one decisive contest'],
      ['clim_confession', 'Confession', 'A truth said aloud breaks everything'],
      ['clim_betrayal', 'Betrayal', 'Trusted figure turns at the worst moment'],
      ['clim_sacrifice', 'Sacrifice', 'Hero pays the ultimate price'],
      ['clim_reveal', 'Reveal', 'Identity / secret bursts into light'],
      ['clim_escape', 'Escape', 'Sequence of survival pressure'],
      ['clim_negotiation', 'Negotiation', 'Words avert (or detonate) catastrophe'],
      ['clim_resurrection', 'Resurrection', 'Dead returns at the breaking point'],
      ['clim_collapse', 'Collapse', 'Whole structure / world falls together'],
    ],
  },

  // ── 17. Resolution Style (10) ──────────────────────────────────────
  {
    id: 'resolution', title: 'Resolution Style', icon: 'checkmark-done', color: '#65A30D',
    hint: 'Where it lands after the climax. Tone of the curtain.',
    items: [
      ['res_triumph', 'Triumph', 'Heroes win; world is better'],
      ['res_pyrrhic', 'Pyrrhic Victory', 'Won, but at unbearable cost'],
      ['res_tragedy', 'Tragedy', 'They lose, the fall is the meaning'],
      ['res_open_ended', 'Open-Ended', 'Future left for the audience'],
      ['res_cycle_renewed', 'Cycle Renewed', 'Same shape, new generation'],
      ['res_status_quo', 'Status Quo Restored', 'Back to before, scarred'],
      ['res_paradigm_shift', 'Paradigm Shift', 'World rewrites its rules'],
      ['res_ascension', 'Ascension', 'Protagonist transcends humanity'],
      ['res_descent', 'Descent', 'Protagonist sinks irreversibly'],
      ['res_ambiguous', 'Ambiguous', 'Outcome cannot be cleanly named'],
    ],
  },

  // ── 18. Moral Framework (12) ───────────────────────────────────────
  {
    id: 'moral', title: 'Moral Framework', icon: 'compass', color: '#0891B2',
    hint: 'Ethics governing the cast. Classic D&D plus formal ethics.',
    items: [
      ['mor_lawful_good', 'Lawful Good', 'Honour, mercy, the just order'],
      ['mor_neutral_good', 'Neutral Good', 'Goodness regardless of rules'],
      ['mor_chaotic_good', 'Chaotic Good', 'Free-spirited do-gooder'],
      ['mor_lawful_neutral', 'Lawful Neutral', 'Order above all'],
      ['mor_true_neutral', 'True Neutral', 'Balance, ambivalence'],
      ['mor_chaotic_neutral', 'Chaotic Neutral', 'Freedom above all'],
      ['mor_lawful_evil', 'Lawful Evil', 'Tyrant, methodical cruelty'],
      ['mor_neutral_evil', 'Neutral Evil', 'Selfish, opportunistic'],
      ['mor_chaotic_evil', 'Chaotic Evil', 'Destruction for its own sake'],
      ['mor_utilitarian', 'Utilitarian', 'Greatest good, do the math'],
      ['mor_deontological', 'Deontological', 'Duty regardless of outcome'],
      ['mor_virtue', 'Virtue Ethics', 'Character over rules or results'],
    ],
  },

  // ── 19. Player Agency (12) ─────────────────────────────────────────
  {
    id: 'agency', title: 'Player Agency', icon: 'options', color: '#7C3AED',
    hint: 'How much the player can steer. Pure choice ⇄ pure railroad.',
    items: [
      ['agc_linear', 'Linear Railroad', 'One path, one ending'],
      ['agc_branching', 'Branching Choices', 'Decisions fork the future'],
      ['agc_open_sandbox', 'Open Sandbox', 'Do anything, anywhere, anytime'],
      ['agc_consequence', 'Consequence Weight', 'Choices ripple far forward'],
      ['agc_dialogue_freedom', 'Dialogue Freedom', 'Speak many ways, many endings'],
      ['agc_silent_protag', 'Silent Protagonist', 'Player projects voice'],
      ['agc_named_protag', 'Named Protagonist', 'Hero has fixed voice and history'],
      ['agc_avatar_customize', 'Customisable Avatar', 'Player builds the body'],
      ['agc_party_mgmt', 'Party Management', 'Many companions, deep maintenance'],
      ['agc_faction_align', 'Faction Alignment', 'Pick a side, reap rewards / hate'],
      ['agc_moral_dial', 'Moral Dial', 'Karma or paragon/renegade gauge'],
      ['agc_replay_value', 'Replay Value', 'New playthroughs reveal new content'],
    ],
  },

  // ── 20. Narrative Structure (12) ───────────────────────────────────
  {
    id: 'structure', title: 'Narrative Structure', icon: 'git-branch', color: '#0EA5E9',
    hint: 'Skeletal blueprint of the storytelling itself.',
    items: [
      ['str_three_act', 'Three-Act', 'Setup, confrontation, resolution'],
      ['str_five_act', 'Five-Act', 'Exposition through dénouement'],
      ['str_kishotenketsu', 'Kishōtenketsu', '4-act no-conflict East Asian'],
      ['str_hero_journey', 'Hero’s Journey', 'Campbell monomyth scaffold'],
      ['str_harmon_circle', 'Harmon Story Circle', 'Eight-beat cyclical template'],
      ['str_seven_point', 'Seven-Point Structure', 'Hook through resolution'],
      ['str_freytag', 'Freytag’s Pyramid', 'Rising / falling action'],
      ['str_in_medias_res', 'In-Medias-Res Frame', 'Open mid-action, fill back'],
      ['str_circular', 'Circular', 'Ends where it began, transformed'],
      ['str_anthology', 'Anthology', 'Discrete tales sharing a theme'],
      ['str_braided', 'Braided', 'Multiple threads weaving together'],
      ['str_mosaic', 'Mosaic', 'Many fragments form one image'],
    ],
  },

  // ── 21. Sensory Palette (18) ───────────────────────────────────────
  {
    id: 'sensory', title: 'Sensory Palette', icon: 'eye', color: '#F59E0B',
    hint: 'What the camera, ear, and skin perceive. Stack for synesthesia.',
    items: [
      ['sens_visual_high', 'Visual: High Detail', 'Dense rendering, every leaf'],
      ['sens_visual_minimal', 'Visual: Minimalist', 'Iconic, sparse, suggestive'],
      ['sens_neon', 'Visual: Neon', 'Saturated electric colour'],
      ['sens_pastel', 'Visual: Pastel', 'Soft, washed, gentle hues'],
      ['sens_monochrome', 'Visual: Monochrome', 'Single hue dominates'],
      ['sens_chiaroscuro', 'Visual: Chiaroscuro', 'Sharp light vs. deep shadow'],
      ['sens_audio_orchestral', 'Audio: Orchestral', 'Sweeping strings + brass'],
      ['sens_audio_electronic', 'Audio: Electronic', 'Synths, beats, machines sing'],
      ['sens_audio_ambient', 'Audio: Ambient', 'Drones, textures, no melody'],
      ['sens_audio_diegetic', 'Audio: Diegetic', 'Only sounds inside the world'],
      ['sens_kin_smooth', 'Feel: Smooth', 'Inputs glide effortlessly'],
      ['sens_kin_punchy', 'Feel: Punchy', 'Snap, crackle, heavy hitstop'],
      ['sens_kin_weighty', 'Feel: Weighty', 'Inertia, momentum, mass'],
      ['sens_kin_floaty', 'Feel: Floaty', 'Light, dreamlike movement'],
      ['sens_olfactory', 'Olfactory Evocation', 'Prose / SFX cue smell'],
      ['sens_gustatory', 'Gustatory Evocation', 'Tastes are described / heard'],
      ['sens_haptic_subtle', 'Haptic: Subtle', 'Light feedback, rare'],
      ['sens_haptic_aggressive', 'Haptic: Aggressive', 'Strong rumble, constant'],
    ],
  },

  // ── 22. Cultural Influences (20) ───────────────────────────────────
  {
    id: 'culture', title: 'Cultural Influences', icon: 'globe', color: '#14B8A6',
    hint: 'Real-world cultural seeds. Combine for fictional hybrids.',
    items: [
      ['cult_norse', 'Norse', 'Long-house, longship, fate-bound'],
      ['cult_celtic', 'Celtic', 'Knotwork, druids, otherworld mounds'],
      ['cult_slavic', 'Slavic', 'Forest spirits, onion domes'],
      ['cult_mediterranean', 'Mediterranean', 'Olive oil, marble, blue water'],
      ['cult_egyptian', 'Egyptian', 'Solar gods, river, embalmed kings'],
      ['cult_mesopotamian', 'Mesopotamian', 'Cuneiform, ziggurats, first cities'],
      ['cult_persian', 'Persian', 'Empire of roads, paradise gardens'],
      ['cult_indian', 'Indian (subcontinental)', 'Cosmologies, cuisine, code of dharma'],
      ['cult_chinese', 'Chinese', 'Dynastic depth, calligraphy, jianghu'],
      ['cult_japanese', 'Japanese', 'Wabi-sabi, kami, edged precision'],
      ['cult_korean', 'Korean', 'Han, hanbok, modern hyperdrive'],
      ['cult_sea', 'Southeast Asian', 'Monsoon, rice terraces, river kings'],
      ['cult_polynesian', 'Polynesian', 'Open-ocean navigation, ancestor mana'],
      ['cult_west_african', 'West African', 'Griots, brass, festival drums'],
      ['cult_east_african', 'East African', 'Rift highlands, swahili traders'],
      ['cult_native_north', 'Native North American', 'Plains, pueblo, longhouse traditions'],
      ['cult_mesoamerican', 'Mesoamerican', 'Maya, Mexica, jade and obsidian'],
      ['cult_andean', 'Andean', 'Quipu, terraces, condor sky'],
      ['cult_arctic', 'Arctic', 'Ice, sea ice, long winter'],
      ['cult_levantine', 'Levantine', 'Caravan crossroads of empires'],
    ],
  },

  // ── 23. Mythos / Cosmology (18) ────────────────────────────────────
  {
    id: 'mythos', title: 'Mythos / Cosmology', icon: 'infinite', color: '#9333EA',
    hint: 'Metaphysical scaffolding. Choose how reality is shaped.',
    items: [
      ['myth_monotheistic', 'Monotheistic', 'One all-encompassing deity'],
      ['myth_pantheonic', 'Pantheonic', 'Multiple gods with portfolios'],
      ['myth_animist', 'Animist', 'Spirit in every thing'],
      ['myth_dualist', 'Dualist', 'Two opposed cosmic principles'],
      ['myth_pantheist', 'Pantheist', 'Universe itself is divine'],
      ['myth_atheist_universe', 'Atheist Universe', 'No gods, no cosmic justice'],
      ['myth_cyclical_time', 'Cyclical Time', 'Ages repeat, eras return'],
      ['myth_linear_time', 'Linear Time', 'Arrow forward, no replay'],
      ['myth_multiverse', 'Multiverse', 'Infinite parallel realities'],
      ['myth_simulation', 'Simulation', 'World is computation by another'],
      ['myth_dream_origin', 'Dream Origin', 'Reality dreamed by a sleeper'],
      ['myth_void_origin', 'Void Origin', 'Born from primordial nothing'],
      ['myth_titans_overthrown', 'Titans Overthrown', 'Old gods deposed by new'],
      ['myth_dying_gods', 'Dying Gods', 'Pantheon fading, magic leaking out'],
      ['myth_new_gods', 'New Gods Ascendant', 'Recently-born divinities rising'],
      ['myth_eldritch', 'Eldritch Beyond', 'Vast indifferent intelligences'],
      ['myth_ancestor_worship', 'Ancestor Worship', 'Dead family are the gods'],
      ['myth_lost_pantheon', 'Lost Pantheon', 'Their names forgotten, power lingers'],
    ],
  },

  // ── 24. Linguistic Style (12) ──────────────────────────────────────
  {
    id: 'linguistic', title: 'Linguistic Style', icon: 'text', color: '#F472B6',
    hint: 'Voice of the prose / dialogue. Bend register and rhythm.',
    items: [
      ['ling_high_register', 'High Register', 'Formal, elevated diction'],
      ['ling_low_register', 'Low Register', 'Vernacular, colloquial'],
      ['ling_archaic', 'Archaic', 'Thee, thou, ye olde'],
      ['ling_modern_vern', 'Modern Vernacular', 'Today’s street speech'],
      ['ling_polyglot', 'Polyglot Mix', 'Many tongues braided'],
      ['ling_conlang', 'Invented Language', 'Constructed in-world tongue'],
      ['ling_dialectal', 'Dialect-Heavy', 'Regional accents on the page'],
      ['ling_jargon', 'Jargon-Heavy', 'Specialist terms thick and proud'],
      ['ling_poetic', 'Poetic', 'Metre, rhyme, lyrical attention'],
      ['ling_terse', 'Terse', 'Short sentences. Like this.'],
      ['ling_baroque', 'Baroque', 'Ornate, looping, opulent'],
      ['ling_idiomatic', 'Idiomatic', 'Steeped in figures of speech'],
    ],
  },

  // ── 25. Time Manipulation (10) ─────────────────────────────────────
  {
    id: 'time', title: 'Time Manipulation', icon: 'time', color: '#0EA5E9',
    hint: 'How chronology behaves in the world or the telling.',
    items: [
      ['time_linear', 'Strict Linear', 'A → B → C, no shuffling'],
      ['time_nonlinear', 'Non-Linear', 'Scenes presented out of order'],
      ['time_loop', 'Time Loop', 'Same window replays'],
      ['time_travel', 'Time Travel', 'Characters move through time'],
      ['time_dilation', 'Time Dilation', 'Subjective time stretches / shrinks'],
      ['time_paradox', 'Paradox-Heavy', 'Causality wraps and bites itself'],
      ['time_stutter', 'Stutter', 'Brief lurches forward or back'],
      ['time_branching', 'Branching Timelines', 'Choices spawn parallel tracks'],
      ['time_rewind', 'Rewind / Undo', 'Player can roll back'],
      ['time_frozen', 'Frozen Moment', 'Whole world pauses for one'],
    ],
  },

  // ── 26. Death & Stakes (10) ────────────────────────────────────────
  {
    id: 'stakes', title: 'Death & Stakes', icon: 'skull', color: '#7F1D1D',
    hint: 'What is risked, what is permanent, what can be undone.',
    items: [
      ['stk_permadeath', 'Permadeath', 'Once gone, gone for good'],
      ['stk_revival_cheap', 'Cheap Revival', 'Death is a minor inconvenience'],
      ['stk_legacy', 'Legacy Continuation', 'Heir picks up the torch'],
      ['stk_cosmic', 'Cosmic Stakes', 'Whole universe on the line'],
      ['stk_personal', 'Personal Stakes', 'One heart hangs in the balance'],
      ['stk_societal', 'Societal Stakes', 'Culture itself may break'],
      ['stk_existential', 'Existential Stakes', 'Identity / meaning at risk'],
      ['stk_slice', 'Low-Stakes Slice', 'A bad day, not the apocalypse'],
      ['stk_sacrificial', 'Sacrificial Stakes', 'Win only by giving something dear'],
      ['stk_fate_unavoid', 'Fate Unavoidable', 'Try as you might, doom comes'],
    ],
  },

  // ── 27. Pacing Curve (10) ──────────────────────────────────────────
  {
    id: 'pacing_curve', title: 'Pacing Curve', icon: 'pulse', color: '#A3E635',
    hint: 'Shape of tension over the whole story. Stack to map a mountain range.',
    items: [
      ['pac_steep_climb', 'Steep Climb', 'Rises hard from the start'],
      ['pac_plateau_peak', 'Plateau Peak', 'Long high tension, then drop'],
      ['pac_double_peak', 'Double Peak', 'Two climaxes, sag between'],
      ['pac_w_pattern', 'W-Pattern', 'Up-down-up-down-up'],
      ['pac_slow_descent', 'Slow Descent', 'Tension drains gradually'],
      ['pac_flatline_burst', 'Flatline + Burst', 'Calm, then sudden eruption'],
      ['pac_zigzag', 'Zig-Zag', 'Constantly swerving tone'],
      ['pac_spiral', 'Spiral', 'Returns to motifs, tightening'],
      ['pac_wave', 'Wave', 'Smooth sinusoidal up and down'],
      ['pac_punc_equilibrium', 'Punctuated Equilibrium', 'Long calm, brief upheaval'],
    ],
  },

  // ── 28. Antagonist Patterns (11) ───────────────────────────────────
  {
    id: 'antagonist', title: 'Antagonist Patterns', icon: 'flame', color: '#991B1B',
    hint: 'Who or what stands against. Stack for hydra-headed opposition.',
    items: [
      ['anta_singular_overlord', 'Singular Overlord', 'One face, one will'],
      ['anta_distributed_evil', 'Distributed Evil', 'No head; corruption everywhere'],
      ['anta_corruption_within', 'Corruption Within', 'Threat from inside the camp'],
      ['anta_indifferent_nature', 'Indifferent Nature', 'World doesn’t care if you live'],
      ['anta_misunderstood', 'Misunderstood Antag', 'Right, from their angle'],
      ['anta_systemic', 'Systemic', 'No villain, just the machine'],
      ['anta_self_destruction', 'Self-Destruction', 'Hero is their own undoing'],
      ['anta_doppelganger', 'Doppelgänger Antag', 'Dark twin of the hero'],
      ['anta_hidden_mastermind', 'Hidden Mastermind', 'Real foe revealed late'],
      ['anta_legion', 'Faceless Legion', 'Numberless, identical foes'],
      ['anta_ideological', 'Ideological', 'Idea, not person, is the enemy'],
    ],
  },

  // ── 29. Combat Style (10) ──────────────────────────────────────────
  {
    id: 'combat', title: 'Combat Style', icon: 'flash-off', color: '#B91C1C',
    hint: 'How violence (or its negation) plays out mechanically and emotionally.',
    items: [
      ['comb_strategic', 'Strategic', 'Map-scale, deliberate, slow'],
      ['comb_tactical', 'Tactical', 'Squad-level chess'],
      ['comb_action', 'Action', 'Twitch reflex, kinetic'],
      ['comb_stealth', 'Stealth', 'Avoid notice, strike from shadow'],
      ['comb_diplomatic', 'Diplomatic Resolution', 'Talk before / instead of blade'],
      ['comb_puzzle', 'Puzzle Resolution', 'Conflicts solved cerebrally'],
      ['comb_ritual', 'Ritual Combat', 'Bound by formal rules'],
      ['comb_mech_scale', 'Mech-Scale', 'Building-sized machines clash'],
      ['comb_kaiju_scale', 'Kaiju-Scale', 'City-block fists hit city-block faces'],
      ['comb_skirmish_scale', 'Skirmish-Scale', 'Small bands, intimate violence'],
    ],
  },

  // ── 30. Exploration Style (8) ──────────────────────────────────────
  {
    id: 'exploration', title: 'Exploration Style', icon: 'compass-outline', color: '#0D9488',
    hint: 'How the world unfolds spatially to the player.',
    items: [
      ['expl_horizontal_open', 'Horizontal Open', 'Vast plains, free roam'],
      ['expl_vertical_open', 'Vertical Open', 'Tower, mountain, sky-ladders'],
      ['expl_metroidvania', 'Metroidvania', 'Gated map, abilities unlock paths'],
      ['expl_linear_corridor', 'Linear Corridor', 'One way through, tight scripting'],
      ['expl_hub_spoke', 'Hub & Spoke', 'Central area branches to missions'],
      ['expl_procedural', 'Procedural', 'Algorithmic worlds, never the same'],
      ['expl_handcrafted_secret', 'Hand-Crafted Secret-Dense', 'Lovingly hidden corners'],
      ['expl_wilderness_survival', 'Wilderness Survival', 'Resources scarce, terrain hostile'],
    ],
  },
];

// ── Derived exports ───────────────────────────────────────────────────
export const NARRATIVE_DNA_KEYS: string[] = NARRATIVE_DNA_GROUPS_DATA
  .flatMap(g => g.items.map(it => it[0]));

export const NARRATIVE_DNA_TOTAL = NARRATIVE_DNA_KEYS.length;

// Dev-time sanity check: keys must be globally unique.
if (typeof __DEV__ !== 'undefined' && __DEV__) {
  const seen = new Set<string>();
  for (const k of NARRATIVE_DNA_KEYS) {
    if (seen.has(k)) {
      // eslint-disable-next-line no-console
      console.warn(`[narrativeDnaData] Duplicate slider key: ${k}`);
    }
    seen.add(k);
  }
}
