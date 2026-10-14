/** Compatibility entrypoint for the governed AI chat workstream.
 * Route renders the server-governed chat controller and immutable conversation replay.
 * Keep legacy Jeeves chat on its existing route until separate migration acceptance.
 * Keep it lazily loaded so Expo Router cold-start remains bounded.
 */
import { makeLazyModalRoute } from '../components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../features/Jeeves/GovernedChatWorkspace'),
  'AIChatRoute',
  'default',
);
