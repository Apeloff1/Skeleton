import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/PhysicsAcademy/PhysicsAcademyModal'), 'PhysicsAcademyRoute', 'PhysicsAcademyModal');
