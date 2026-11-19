import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/ReadingCorner/ReadingCornerModal'), 'ReadingCornerRoute', 'ReadingCornerModal');
