import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/MultiAgent/MultiAgentModal'), 'MultiAgentRoute', 'MultiAgentModal');
