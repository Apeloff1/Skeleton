import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/AIGameGenerator/AIGameGeneratorModal'), 'AIGameGeneratorRoute', 'AIGameGeneratorModal');
