import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/ReferenceHub/ReferenceHubModal'), 'ReferenceRoute', 'ReferenceHubModal');
