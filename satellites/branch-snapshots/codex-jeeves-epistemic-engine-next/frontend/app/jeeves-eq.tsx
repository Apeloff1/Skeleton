import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/JeevesEQ/JeevesEQModal'), 'JeevesEQRoute', 'JeevesEQModal');
