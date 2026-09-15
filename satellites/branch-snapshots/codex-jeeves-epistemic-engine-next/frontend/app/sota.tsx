import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/SOTA/SOTAModal'), 'SOTARoute', 'SOTAModal');
