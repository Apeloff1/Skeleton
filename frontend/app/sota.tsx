import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/SOTA/SOTAModal'), 'SOTARoute', 'SOTAModal');
