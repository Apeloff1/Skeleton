import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/RosettaPlayground/RosettaPlaygroundModal'), 'RosettaPlaygroundRoute', 'RosettaPlaygroundModal');
