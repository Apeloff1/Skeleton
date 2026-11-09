use std::collections::HashMap;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MotionStatus { Tabled, Resolved, Rejected }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Motion {
    pub id: String,
    pub session_id: String,
    pub text: String,
    pub mover: String,
    pub tabled_at: DateTime<Utc>,
    pub status: MotionStatus,
    pub resolution_event: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Session {
    pub id: String,
    pub title: String,
    pub agenda: Vec<String>,
    pub opened: DateTime<Utc>,
    pub closed: Option<DateTime<Utc>>,
    pub chair: String,
}

pub struct Boardroom {
    sessions: RwLock<HashMap<String, Session>>,
    motions: RwLock<HashMap<String, Motion>>,
}

impl Default for Boardroom { fn default() -> Self { Self::new() } }
impl Boardroom {
    pub fn new() -> Self { Self { sessions: RwLock::new(HashMap::new()), motions: RwLock::new(HashMap::new()) } }
    pub async fn convene(&self, title: &str, chair: &str, agenda: Vec<String>) -> Session {
        let session = Session { id: Uuid::new_v4().to_string(), title: title.to_string(), agenda, opened: Utc::now(), closed: None, chair: chair.to_string() };
        self.sessions.write().await.insert(session.id.clone(), session.clone());
        session
    }
    pub async fn table_motion(&self, session_id: &str, mover: &str, text: &str) -> Option<(Motion, String)> {
        let sessions = self.sessions.read().await;
        let session = sessions.get(session_id)?;
        if session.closed.is_some() { return None; }
        drop(sessions);
        let motion = Motion { id: Uuid::new_v4().to_string(), session_id: session_id.to_string(), text: text.to_string(), mover: mover.to_string(), tabled_at: Utc::now(), status: MotionStatus::Tabled, resolution_event: None };
        let proposal_id = format!("motion:{}", motion.id);
        self.motions.write().await.insert(motion.id.clone(), motion.clone());
        Some((motion, proposal_id))
    }
    pub async fn resolve_motion(&self, motion_id: &str, carried: bool, event_id: Option<String>) -> Option<Motion> {
        let mut motions = self.motions.write().await;
        let m = motions.get_mut(motion_id)?;
        if m.status != MotionStatus::Tabled { return None; }
        m.status = if carried { MotionStatus::Resolved } else { MotionStatus::Rejected };
        m.resolution_event = event_id;
        Some(m.clone())
    }
    pub async fn adjourn(&self, session_id: &str) -> Option<Session> {
        let mut sessions = self.sessions.write().await;
        let s = sessions.get_mut(session_id)?;
        if s.closed.is_some() { return None; }
        s.closed = Some(Utc::now());
        Some(s.clone())
    }
    pub async fn session_motions(&self, session_id: &str) -> Vec<Motion> {
        self.motions.read().await.values().filter(|m| m.session_id == session_id).cloned().collect()
    }
    pub async fn sessions(&self) -> Vec<Session> { self.sessions.read().await.values().cloned().collect() }
}
