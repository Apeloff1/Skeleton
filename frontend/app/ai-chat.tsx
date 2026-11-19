/** Entry point for the governed AI chat workstream.
 * The server-authorized conversation, model inventory and replay controller live
 * in GovernedChatWorkspace. Keep legacy Jeeves chat on /jeeves-chat.
 * Lazily load the governed workspace so Expo Router startup remains bounded.
 */
import React from 'react';
import StudioLoginGate from '../src/auth/StudioLoginGate';
import { makeLazyModalRoute } from '../components/SafeModalRoute';

const GovernedChatRoute = makeLazyModalRoute(
  () => import('../features/Jeeves/GovernedChatWorkspace'),
  'AIChatRoute',
  'default',
);

export default function AIChatRoute() {
  return <StudioLoginGate title="Conversation workspace" requireAuthenticated><GovernedChatRoute /></StudioLoginGate>;
}
