import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/KnowledgeDatabases/KnowledgeDatabasesModal'), 'KnowledgeDatabasesRoute', 'KnowledgeDatabasesModal');
