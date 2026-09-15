import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Jeeves/JeevesModal'), 'JeevesRoute', 'JeevesModal');
