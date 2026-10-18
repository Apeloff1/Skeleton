import { makeLazyModalRoute } from '../src/components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../src/features/GameFactory/GameFactoryRouteModal'),
  'GameFactoryRoute',
  'GameFactoryRouteModal',
);
