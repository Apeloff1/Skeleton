import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/BugfixLibrary/BugfixLibraryModal'), 'BugfixLibraryRoute', 'BugfixLibraryModal');
