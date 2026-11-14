/**
 * Explicit bridge from the entire historical Galaxy Studio picker to
 * the 158 recognized GameForge brief genre choices. Mapping is intentional, not a
 * claim that the condensed archetype reproduces each complete game's systems.
 */
import { FALLBACK_GENRES } from '../features/GalaxyStudioFactory/fallbackGenres';

export const GALAXY_TO_FORGE_BRIEF: Record<string, string> = {
  platformer_2d: 'platformer', platformer_3d: 'platformer',
  rpg: 'rpg', fps: 'fps', tps: 'shooter',
  battle_royale: 'battle-royale', mmorpg: 'mmorpg', moba: 'strategy',
  puzzle: 'puzzle', strategy_rts: 'rts', turn_based_strategy: 'tactics',
  four_x: 'strategy', grand_strategy: 'strategy', colony_sim: 'simulation',
  automation: 'simulation', survival: 'survival', soulslike: 'soulslike',
  metroidvania: 'metroidvania', roguelike: 'roguelike', deckbuilder: 'deckbuilder',
  fighting: 'fighting', racing: 'simulation', horror: 'horror',
  stealth: 'stealth', simulation: 'simulation', city_builder: 'city-builder',
  farming_sim: 'cozy', sandbox: 'simulation', visual_novel: 'visual-novel',
  rhythm: 'arcade', tower_defense: 'strategy', sports: 'simulation',
  extraction_shooter: 'extraction', social_deduction: 'narrative',
  idle_clicker: 'simulation', gacha: 'rpg', space_sim: 'simulation',
  flight_sim: 'simulation', naval_pirate: 'action-adventure',
  party_game: 'arcade', educational: 'puzzle', cozy_game: 'cozy',
  hunting: 'survival', fishing: 'cozy', mech_robot: 'shooter',
  bullet_hell: 'bullet-heaven', walking_sim: 'narrative',
  point_and_click: 'adventure', auto_battler: 'tactics',
  dating_sim: 'visual-novel', vehicle_combat: 'shooter',
  immersive_sim: 'immersive-sim', tycoon: 'simulation',
  management_sim: 'simulation', mmo: 'mmo',
  action_adventure: 'action-adventure', open_world: 'action-adventure',
  looter_shooter: 'shooter', extraction_rpg: 'extraction',
  card_game: 'card', board_game: 'puzzle', text_adventure: 'narrative',
  roguelite_shooter: 'roguelite', beat_em_up: 'beat-em-up',
  shoot_em_up: 'shoot-em-up', twin_stick: 'shooter',
  stealth_action: 'stealth', tactics: 'tactics',
  metaverse_social: 'mmo',
};

export const GALAXY_CHOICES = FALLBACK_GENRES.map(({ id, name, desc }) => ({ id, name, desc }));
const known = new Map(GALAXY_CHOICES.map((g) => [g.id, g]));

export function galaxyGenre(id: string | null | undefined) {
  return typeof id === 'string' ? known.get(id) ?? null : null;
}
export function mappedBriefGenre(id: string | null | undefined): string | null {
  return id && galaxyGenre(id) ? GALAXY_TO_FORGE_BRIEF[id] ?? null : null;
}
export function specializedVision(vision: string, id: string | null | undefined, max = 4000): string {
  const original = vision.trim().slice(0, max);
  const selection = galaxyGenre(id);
  if (!selection) return original;
  const suffix = 'Specialized genre: ' + selection.name + '.';
  // Never truncate user-authored vision to fit a generated descriptor.
  if (original && original.length + suffix.length + 1 > max) return original;
  return original ? original + '\n' + suffix : suffix;
}
