import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/GameFactory/GameFactoryModal'), 'GameFactoryRoute', 'GameFactoryModal');
