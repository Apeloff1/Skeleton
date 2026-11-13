import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/RosettaPlayground/RosettaPlaygroundModal'), 'RosettaPlaygroundRoute', 'RosettaPlaygroundModal');
