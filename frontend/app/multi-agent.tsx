import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/MultiAgent/MultiAgentModal'), 'MultiAgentRoute', 'MultiAgentModal');
