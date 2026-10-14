/** Entry point for the governed AI chat workstream.
 * The server-authorized conversation, model inventory and replay controller live
 * in GovernedChatWorkspace. Keep legacy Jeeves chat on /jeeves-chat.
 * Lazily load the governed workspace so Expo Router startup remains bounded.
 */
import { makeLazyModalRoute } from '../components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../features/Jeeves/GovernedChatWorkspace'),
  'AIChatRoute',
  'default',
);
