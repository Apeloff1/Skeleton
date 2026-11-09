import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/AI/AISuggestionsModal'), 'AISuggestionsRoute', 'AISuggestionsModal');
