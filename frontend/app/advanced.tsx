import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Advanced/AdvancedFeaturesModal'), 'AdvancedFeaturesRoute', 'AdvancedFeaturesModal');
