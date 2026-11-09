import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/ThermalMonitor/ThermalMonitorModal'), 'ThermalRoute', 'ThermalMonitorModal');
