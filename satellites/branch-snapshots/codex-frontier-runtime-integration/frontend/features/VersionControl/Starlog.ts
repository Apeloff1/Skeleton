// ============================================================================
// CODEDOCK QUANTUM NEXUS - Version Control System (Starlog)
// Git-like versioning via IndexedDB with branching, snapshots, rollback
// ============================================================================

import AsyncStorage from '@react-native-async-storage/async-storage';

// ============================================================================
// TYPES
// ============================================================================
export interface Snapshot {
  id: string;
  name: string;
  message: string;
  timestamp: Date;
  code: string;
  language: string;
  fileName: string;
  branch: string;
  parentId: string | null;
  hash: string;
  metadata: {
    linesAdded: number;
    linesRemoved: number;
    optimizationLevel?: string;
    sanitizers?: string[];
  };
}

export interface Branch {
  name: string;
  headId: string | null;
  createdAt: Date;
  description?: string;
  isProtected: boolean;
}

export interface Mission {
  id: string;
  name: string;
  description: string;
  createdAt: Date;
  updatedAt: Date;
  branches: Branch[];
  currentBranch: string;
  snapshots: Snapshot[];
  tags: Record<string, string>; // tag name -> snapshot id
}

export interface StarlogExport {
  version: string;
  exportedAt: Date;
  mission: Mission;
}

export interface DiffResult {
  added: string[];
  removed: string[];
  unchanged: string[];
  stats: {
    additions: number;
    deletions: number;
    totalChanges: number;
  };
}

// ============================================================================
// STORAGE KEYS
// ============================================================================
const STORAGE_KEYS = {
  MISSIONS: '@starlog_missions',
  CURRENT_MISSION: '@starlog_current_mission',
  SETTINGS: '@starlog_settings',
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================
function generateId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).substr(2, 9)}`;
}

function generateHash(content: string): string {
  let hash = 0;
  for (let i = 0; i < content.length; i++) {
    const char = content.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).padStart(8, '0');
}

function computeDiff(oldCode: string, newCode: string): DiffResult {
  const oldLines = oldCode.split('\n');
  const newLines = newCode.split('\n');
  
  const oldSet = new Set(oldLines);
  const newSet = new Set(newLines);
  
  const added = newLines.filter(line => !oldSet.has(line));
  const removed = oldLines.filter(line => !newSet.has(line));
  const unchanged = newLines.filter(line => oldSet.has(line));
  
  return {
    added,
    removed,
    unchanged,
    stats: {
      additions: added.length,
      deletions: removed.length,
      totalChanges: added.length + removed.length,
    },
  };
}

// ============================================================================
// STARLOG VERSION CONTROL CLASS
// ============================================================================
export class Starlog {
  private missions: Map<string, Mission> = new Map();
  private currentMissionId: string | null = null;
  
  async initialize(): Promise<void> {
    try {
      const missionsJson = await AsyncStorage.getItem(STORAGE_KEYS.MISSIONS);
      if (missionsJson) {
        const missionsArray: Mission[] = JSON.parse(missionsJson);
        missionsArray.forEach(m => {
          // Restore dates
          m.createdAt = new Date(m.createdAt);
          m.updatedAt = new Date(m.updatedAt);
          m.snapshots.forEach(s => s.timestamp = new Date(s.timestamp));
          m.branches.forEach(b => b.createdAt = new Date(b.createdAt));
          this.missions.set(m.id, m);
        });
      }
      
      const currentId = await AsyncStorage.getItem(STORAGE_KEYS.CURRENT_MISSION);
      if (currentId && this.missions.has(currentId)) {
        this.currentMissionId = currentId;
      }
    } catch (e) {
      console.error('Failed to initialize Starlog:', e);
    }
  }
  
  async save(): Promise<void> {
    try {
      const missionsArray = Array.from(this.missions.values());
      await AsyncStorage.setItem(STORAGE_KEYS.MISSIONS, JSON.stringify(missionsArray));
      if (this.currentMissionId) {
        await AsyncStorage.setItem(STORAGE_KEYS.CURRENT_MISSION, this.currentMissionId);
      }
    } catch (e) {
      console.error('Failed to save Starlog:', e);
    }
  }
  
  // ============================================================================
  // MISSION OPERATIONS
  // ============================================================================
  createMission(name: string, description: string = ''): Mission {
    const mission: Mission = {
      id: generateId(),
      name,
      description,
      createdAt: new Date(),
      updatedAt: new Date(),
      branches: [
        { name: 'main', headId: null, createdAt: new Date(), isProtected: true, description: 'Main branch' }
      ],
      currentBranch: 'main',
      snapshots: [],
      tags: {},
    };
    
    this.missions.set(mission.id, mission);
    this.currentMissionId = mission.id;
    this.save();
    
    return mission;
  }
  
  getMission(id: string): Mission | undefined {
    return this.missions.get(id);
  }
  
  getCurrentMission(): Mission | null {
    if (!this.currentMissionId) return null;
    return this.missions.get(this.currentMissionId) || null;
  }
  
  getAllMissions(): Mission[] {
    return Array.from(this.missions.values());
  }
  
  deleteMission(id: string): boolean {
    const deleted = this.missions.delete(id);
    if (this.currentMissionId === id) {
      const firstKey = this.missions.keys().next();
      this.currentMissionId = this.missions.size > 0 && !firstKey.done ? firstKey.value : null;
    }
    this.save();
    return deleted;
  }
  
  switchMission(id: string): boolean {
    if (!this.missions.has(id)) return false;
    this.currentMissionId = id;
    this.save();
    return true;
  }
  
  // ============================================================================
  // SNAPSHOT OPERATIONS
  // ============================================================================
  createSnapshot(
    code: string,
    language: string,
    fileName: string,
    message: string,
    name?: string,
    metadata?: Partial<Snapshot['metadata']>
  ): Snapshot | null {
    const mission = this.getCurrentMission();
    if (!mission) return null;
    
    const branch = mission.branches.find(b => b.name === mission.currentBranch);
    if (!branch) return null;
    
    // Get parent snapshot for diff
    const parentSnapshot = branch.headId ? mission.snapshots.find(s => s.id === branch.headId) : null;
    const diff = parentSnapshot ? computeDiff(parentSnapshot.code, code) : { stats: { additions: code.split('\n').length, deletions: 0 } };
    
    const snapshot: Snapshot = {
      id: generateId(),
      name: name || `snapshot-${mission.snapshots.length + 1}`,
      message,
      timestamp: new Date(),
      code,
      language,
      fileName,
      branch: mission.currentBranch,
      parentId: branch.headId,
      hash: generateHash(code + message + Date.now()),
      metadata: {
        linesAdded: diff.stats.additions,
        linesRemoved: diff.stats.deletions,
        ...metadata,
      },
    };
    
    mission.snapshots.push(snapshot);
    branch.headId = snapshot.id;
    mission.updatedAt = new Date();
    
    this.save();
    return snapshot;
  }
  
  getSnapshot(id: string): Snapshot | null {
    const mission = this.getCurrentMission();
    if (!mission) return null;
    return mission.snapshots.find(s => s.id === id) || null;
  }
  
  getSnapshotsByBranch(branchName: string): Snapshot[] {
    const mission = this.getCurrentMission();
    if (!mission) return [];
    return mission.snapshots.filter(s => s.branch === branchName).sort((a, b) => 
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }
  
  getHistory(limit: number = 50): Snapshot[] {
    const mission = this.getCurrentMission();
    if (!mission) return [];
    
    const branchSnapshots = this.getSnapshotsByBranch(mission.currentBranch);
    return branchSnapshots.slice(0, limit);
  }
  
  rollback(snapshotId: string): { code: string; language: string; fileName: string } | null {
    const snapshot = this.getSnapshot(snapshotId);
    if (!snapshot) return null;
    
    return {
      code: snapshot.code,
      language: snapshot.language,
      fileName: snapshot.fileName,
    };
  }
  
  // ============================================================================
  // BRANCH OPERATIONS
  // ============================================================================
  createBranch(name: string, description?: string, fromSnapshot?: string): Branch | null {
    const mission = this.getCurrentMission();
    if (!mission) return null;
    
    // Check if branch already exists
    if (mission.branches.some(b => b.name === name)) return null;
    
    const currentBranch = mission.branches.find(b => b.name === mission.currentBranch);
    const headId = fromSnapshot || currentBranch?.headId || null;
    
    const branch: Branch = {
      name,
      headId,
      createdAt: new Date(),
      description,
      isProtected: false,
    };
    
    mission.branches.push(branch);
    mission.currentBranch = name;
    mission.updatedAt = new Date();
    
    this.save();
    return branch;
  }
  
  switchBranch(name: string): boolean {
    const mission = this.getCurrentMission();
    if (!mission) return false;
    
    if (!mission.branches.some(b => b.name === name)) return false;
    
    mission.currentBranch = name;
    this.save();
    return true;
  }
  
  deleteBranch(name: string): boolean {
    const mission = this.getCurrentMission();
    if (!mission) return false;
    
    const branch = mission.branches.find(b => b.name === name);
    if (!branch || branch.isProtected) return false;
    
    mission.branches = mission.branches.filter(b => b.name !== name);
    
    if (mission.currentBranch === name) {
      mission.currentBranch = 'main';
    }
    
    this.save();
    return true;
  }
  
  getBranches(): Branch[] {
    const mission = this.getCurrentMission();
    return mission?.branches || [];
  }
  
  getCurrentBranch(): Branch | null {
    const mission = this.getCurrentMission();
    if (!mission) return null;
    return mission.branches.find(b => b.name === mission.currentBranch) || null;
  }
  
  // ============================================================================
  // TAG OPERATIONS
  // ============================================================================
  createTag(name: string, snapshotId?: string): boolean {
    const mission = this.getCurrentMission();
    if (!mission) return false;
    
    const targetId = snapshotId || this.getCurrentBranch()?.headId;
    if (!targetId) return false;
    
    mission.tags[name] = targetId;
    this.save();
    return true;
  }
  
  deleteTag(name: string): boolean {
    const mission = this.getCurrentMission();
    if (!mission) return false;
    
    if (!(name in mission.tags)) return false;
    
    delete mission.tags[name];
    this.save();
    return true;
  }
  
  getTags(): Record<string, string> {
    const mission = this.getCurrentMission();
    return mission?.tags || {};
  }
  
  // ============================================================================
  // DIFF & COMPARE
  // ============================================================================
  compare(snapshotId1: string, snapshotId2: string): DiffResult | null {
    const s1 = this.getSnapshot(snapshotId1);
    const s2 = this.getSnapshot(snapshotId2);
    
    if (!s1 || !s2) return null;
    
    return computeDiff(s1.code, s2.code);
  }
  
  // ============================================================================
  // EXPORT/IMPORT
  // ============================================================================
  exportMission(missionId?: string): StarlogExport | null {
    const mission = missionId ? this.getMission(missionId) : this.getCurrentMission();
    if (!mission) return null;
    
    return {
      version: '1.0.0',
      exportedAt: new Date(),
      mission: JSON.parse(JSON.stringify(mission)),
    };
  }
  
  exportToStarlog(missionId?: string): string | null {
    const exportData = this.exportMission(missionId);
    if (!exportData) return null;
    
    return JSON.stringify(exportData, null, 2);
  }
  
  async importFromStarlog(starlogJson: string): Promise<Mission | null> {
    try {
      const data: StarlogExport = JSON.parse(starlogJson);
      
      // Validate
      if (!data.mission || !data.version) return null;
      
      // Generate new ID to avoid conflicts
      const mission = data.mission;
      mission.id = generateId();
      mission.createdAt = new Date(mission.createdAt);
      mission.updatedAt = new Date();
      mission.snapshots.forEach(s => s.timestamp = new Date(s.timestamp));
      mission.branches.forEach(b => b.createdAt = new Date(b.createdAt));
      
      this.missions.set(mission.id, mission);
      this.currentMissionId = mission.id;
      await this.save();
      
      return mission;
    } catch (e) {
      console.error('Failed to import Starlog:', e);
      return null;
    }
  }
}

// ============================================================================
// SINGLETON INSTANCE
// ============================================================================
export const starlog = new Starlog();

export default starlog;
