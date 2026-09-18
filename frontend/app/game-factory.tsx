import { makeLazyModalRoute } from '../components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../features/GameFactory/GameFactoryRouteModal'),
  'GameFactoryRoute',
  'GameFactoryRouteModal',
);
