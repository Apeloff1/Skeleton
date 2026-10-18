import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/GroupChat/GroupChatModal'), 'GroupChatRoute', 'GroupChatModal');
