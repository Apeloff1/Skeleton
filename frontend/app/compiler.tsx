import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Compiler/CompilerModal'), 'CompilerRoute', 'CompilerModal', { onApplyFix: () => {} } as any);
