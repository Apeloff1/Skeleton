import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/AI/AISuggestionsModal'), 'AISuggestionsRoute', 'AISuggestionsModal');
