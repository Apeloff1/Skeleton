import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/Advanced/AdvancedFeaturesModal'), 'AdvancedFeaturesRoute', 'AdvancedFeaturesModal');
