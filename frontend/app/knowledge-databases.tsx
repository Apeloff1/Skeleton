import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/KnowledgeDatabases/KnowledgeDatabasesModal'), 'KnowledgeDatabasesRoute', 'KnowledgeDatabasesModal');
