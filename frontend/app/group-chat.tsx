import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/GroupChat/GroupChatModal'), 'GroupChatRoute', 'GroupChatModal');
