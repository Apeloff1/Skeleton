import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/BugfixLibrary/BugfixLibraryModal'), 'BugfixLibraryRoute', 'BugfixLibraryModal');
