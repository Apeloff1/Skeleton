import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/SOTAExtended/SOTAExtendedModal'), 'SOTAExtendedRoute', 'SOTAExtendedModal');
