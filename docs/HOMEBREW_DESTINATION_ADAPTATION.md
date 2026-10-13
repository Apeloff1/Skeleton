# Original-homebrew destination adaptation: native Windows enhancements

## Homebrew and clean-room legal boundary

Production only accepts wholly original homebrew capsules. A "clone"
mode cannot import or reproduce a commercial game's protected
expression, sprites, music, characters, source, branding, game files
or level data. The available CLEAN-ROOM SPIRITUAL SUCCESSOR mode creates
a new original presentation inspired only by general ideas and
mechanics. This is not a copyright-circumvention feature or guarantee:
an author can lie about originality, and trademark and copyright
review remains necessary.

This conservative policy is stricter than some lawful licenses:
third-party and open-licensed commercial material still cannot cross
into the production plane. EU Directive 2009/24/EC Article 6 prohibits
misusing interoperability information to develop software
substantially similar in expression. US 17 USC 102(b) excludes abstract
procedures, systems and methods from copyright, but protects original
expression under 102(a).

Official references:
- https://eur-lex.europa.eu/legal-content/en/TXT/?uri=CELEX%3A32009L0024
- https://www.govinfo.gov/content/pkg/USCODE-2024-title17/html/USCODE-2024-title17-chap1-sec102.htm

## Source physics stays true; destination can surpass source visuals

Original homebrew input retains exact source tile SHA-256, original
spawn/goal, collision geometry, integer platformer physics and
replayed original winning controller inputs. Its rights manifest is
independently rechecked whenever a port is compiled or launched.

The first actual port destination is WINDOWS-NATIVE. Additional
console/PC systems are not represented as verified exporters until
working binaries, appropriate SDK licenses, hardware acceptance and
publication rights are independently demonstrated.

Enhanced Windows rendering includes:
- Seven distinctly original art directions: Pixel Heritage,
  Neon Noir, Storybook, Handheld Amber, Vector Celestial,
  Monochrome Ink, and Soft Pastel.
- Three graphics budgets: Balanced, Enhanced, Cinematic.
- 16–56 pixels per grid tile, adjustable upscaling.
- Procedural original decorative particles, original character art,
  layered tile bevels, goal glows, camera positioning and parallax.
- Real reduced-motion mode, high-contrast and colorblind-safe palette
  overrides, optional heads-up display, independent rendering
  cadence from the original deterministic simulation.

These choices are genuinely rendered by the native Tk canvas;
they are not HTML mockups or copied graphics. They are a bounded
software raster-style UI, not GPU ray tracing or unverified
performance on every consumer-grade PC.

## Five independently implemented hybrid mechanics

1. Collectathon — original reachable items and awarded points.
2. Keyquest — collection of all route-placed keys gates game victory.
3. Speedrun — actual controller-frame par, elapsed frames and medal.
4. Exploration — player-visited map cells and original fog of war.
5. Combo — successive pickup multipliers and bonus score.

All five may be combined for a cross-hybrid. Two separate native
gameplay simulations must produce the same complete frame trace and
reach the hybrid victory. If key placement or gameplay cannot pass the
baseline controller route, generation is rejected.

Original creative choices are Faithful Homebrew (no genre hybrid),
Enhanced Homebrew, Hybrid Original, and Clean-Room Spiritual Successor.
The latter is an independent original creative methodology, not a
skin-changing commercial ROM clone or automatic legal clearance.

## Use the tools

Create your original platformer project:

~~~sh
PYTHONPATH=. python scripts/game/game_project.py \
 --demo-project original.json --seed 42 \
 --targets windows-11,chip8-vip
~~~

Make a sophisticated Windows hybrid using actual original gameplay:

~~~sh
PYTHONPATH=. python scripts/game/port_homebrew.py \
 --capsule original.json --output windows-port.json \
 --destination windows-native \
 --creative-mode hybrid_original \
 --art-direction neon_noir --quality cinematic \
 --hybrids collectathon,keyquest,speedrun,exploration,combo \
 --scale 40 --decor-budget 36 --high-contrast
~~~

Verify determinism and rights against the original project:

~~~sh
PYTHONPATH=. python scripts/game/port_homebrew.py \
 --capsule original.json --verify windows-port.json
~~~

Play upgraded game using the ACTUAL Windows native game executable:

~~~powershell
SkeletonGame.exe --project original.json --port-blueprint windows-port.json
~~~

Verify through the installed headless offline executable:

~~~powershell
SkeletonOffline.exe --homebrew-port-check --homebrew-port-project original.json --homebrew-port-blueprint windows-port.json --json
~~~

The native original-game editor also has a separate Windows Port Studio
dialog with art direction, three quality levels, all five hybrid
toggles, seed, scalable tile size, particle/detail budget,
reduced motion, contrast, colorblind-safe hues, parallax, HUD,
distinct Save As project/port paths and reproducible gameplay QA.
No output overwrites source or publishes unapproved content.

## Reversible keyquest and executed acceptance

The destination-specific keyquest gate prevents an **unwinnable
terminal state**: reaching the original goal before collecting every
homebrew key returns the player to the last legal cell and records a
locked-goal attempt. After collecting keys, the exact same original
goal remains available. No copyrighted art, new training data or
replacement source physics is introduced.

The completion gate now executes four original-game outputs:
real ISO C89 executable to WIN, actual CHIP-8 homebrew ROM bytes to
WIN, native 2D deterministic gameplay to WIN, and enhanced native
Windows gameplay with all five hybrids to WIN. Installed Windows
packaging, real desktop display, independent compatibility testing
and human rights clearance remain separate release prerequisites.

## Honest completion and resource accounting

The working implementation is a destination blueprint interpreted
by the existing SkeletonGame.exe. It is not yet a separately compiled
standalone installer per game, and the Windows GUI still requires
actual desktop acceptance beyond headless replay.

CHIP-8 homebrew ROM and generic C89 turn-based source remain distinct
working output paths. Other console-native exporters still require
technical and rights validation. Upgrades generate NO model-training
records: the synthetic reference bank and sparse 36-example default
are unchanged.
