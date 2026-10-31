import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/ReferenceHub/ReferenceHubModal'), 'ReferenceRoute', 'ReferenceHubModal');
