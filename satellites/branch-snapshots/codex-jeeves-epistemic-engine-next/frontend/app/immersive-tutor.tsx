import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/ImmersiveTutor/ImmersiveTutorModal'), 'ImmersiveTutorRoute', 'ImmersiveTutorModal');
