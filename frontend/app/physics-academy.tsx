import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/PhysicsAcademy/PhysicsAcademyModal'), 'PhysicsAcademyRoute', 'PhysicsAcademyModal');
