/**
 * Deliberately sparse bridging hints from the 67 historical Galaxy genres to
 * eight actually implemented Godot mini-games. A hint is not equivalent
 * gameplay coverage: never auto-enable or silently rewrite creator intent.
 */
import { galaxyGenre } from './galaxyGenres';

export const PLAYABLE_GENRE_HINTS: Readonly<Record<string, string>> = Object.freeze({
  puzzle: 'puzzle',
  point_and_click: 'puzzle',
  educational: 'puzzle',
  board_game: 'puzzle',
  racing: 'racing',
  survival: 'survival',
  hunting: 'survival',
  stealth: 'stealth',
  stealth_action: 'stealth',
  farming_sim: 'crafting',
  cozy_game: 'crafting',
  automation: 'pipeline',
  colony_sim: 'pipeline',
  management_sim: 'pipeline',
  tycoon: 'pipeline',
  city_builder: 'pipeline',
  fighting: 'combat_loop',
  extraction_shooter: 'extraction',
  extraction_rpg: 'extraction',
  looter_shooter: 'extraction',
});

export function suggestPlayableMode(genreId: string | null | undefined):
  { genre: string; genreName: string; mode: string } | null {
  const genre = galaxyGenre(genreId);
  if (!genre) return null;
  const mode = PLAYABLE_GENRE_HINTS[genre.id];
  if (!mode) return null;
  return { genre: genre.id, genreName: genre.name, mode };
}
