import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/AIInteractionsLog/AIInteractionsLogModal'), 'AIInteractionsLogRoute', 'AIInteractionsLogModal');
