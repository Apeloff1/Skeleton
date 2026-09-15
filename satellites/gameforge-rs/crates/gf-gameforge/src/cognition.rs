use std::collections::HashMap;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Evidence { pub witness: String, pub polarity: bool, pub weight: f64, pub at: DateTime<Utc> }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Belief {
    pub id: String, pub predicate: String, pub polarity: bool, pub lodds: f64,
    pub evidence: Vec<Evidence>, pub created: DateTime<Utc>, pub touched: DateTime<Utc>,
}
impl Belief { pub fn confidence(&self) -> f64 { 1.0 / (1.0 + (-self.lodds).exp()) } }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Schism { pub predicate: String, pub supporting: Vec<String>, pub refuting: Vec<String>, pub detected: DateTime<Utc> }
const WITNESS_STEP: f64 = 1.2;
const CONVICTION: f64 = 0.3;
const DECAY_PER_DAY: f64 = 0.05;
const LEDGER_CAP: usize = 8192;

pub struct Cognition { beliefs: RwLock<HashMap<String, Belief>>, schisms: RwLock<Vec<Schism>> }
impl Default for Cognition { fn default() -> Self { Self::new() } }
impl Cognition {
    pub fn new() -> Self { Self { beliefs: RwLock::new(HashMap::new()), schisms: RwLock::new(Vec::new()) } }
    pub async fn hold(&self, predicate: &str, polarity: bool) -> String {
        let mut beliefs = self.beliefs.write().await;
        for b in beliefs.values() { if b.predicate == predicate && b.polarity == polarity { return b.id.clone(); } }
        if beliefs.len() >= LEDGER_CAP {
            let mut by_conviction: Vec<(String, f64)> = beliefs.iter().map(|(id,b)|(id.clone(), b.lodds.abs())).collect();
            by_conviction.sort_by(|a,b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
            for (id,_) in by_conviction.into_iter().take(LEDGER_CAP / 4) { beliefs.remove(&id); }
        }
        let id = Uuid::new_v4().to_string();
        beliefs.insert(id.clone(), Belief { id: id.clone(), predicate: predicate.to_string(), polarity, lodds: 0.0, evidence: Vec::new(), created: Utc::now(), touched: Utc::now() });
        id
    }
    pub async fn testify(&self, belief_id: &str, witness: &str, supports: bool, weight: f64) -> Option<f64> {
        let weight = weight.clamp(0.0,1.0);
        let mut beliefs = self.beliefs.write().await;
        let now = Utc::now();
        let b = beliefs.get_mut(belief_id)?;
        let days = (now - b.touched).num_seconds() as f64 / 86400.0;
        if days > 0.0 { b.lodds *= (1.0 - DECAY_PER_DAY * days).max(0.0); }
        let prior = b.evidence.iter().filter(|e| e.witness == witness).count() as f64;
        let voice = weight / (1.0 + prior);
        b.lodds = (b.lodds + WITNESS_STEP * voice * if supports {1.0} else {-1.0}).clamp(-8.0,8.0);
        b.evidence.push(Evidence { witness: witness.to_string(), polarity: supports, weight, at: now });
        b.touched = now;
        let predicate = b.predicate.clone();
        let confidence = b.confidence();
        drop(beliefs);
        self.scan_schism(&predicate).await;
        Some(confidence)
    }
    async fn scan_schism(&self, predicate: &str) {
        let beliefs = self.beliefs.read().await;
        let supporting: Vec<String> = beliefs.values().filter(|b| b.predicate == predicate && b.polarity && b.confidence() >= 0.5 + CONVICTION).map(|b|b.id.clone()).collect();
        let refuting: Vec<String> = beliefs.values().filter(|b| b.predicate == predicate && !b.polarity && b.confidence() >= 0.5 + CONVICTION).map(|b|b.id.clone()).collect();
        drop(beliefs);
        if supporting.is_empty() || refuting.is_empty() { return; }
        let mut schisms = self.schisms.write().await;
        if !schisms.iter().any(|s| s.predicate == predicate) {
            schisms.push(Schism { predicate: predicate.to_string(), supporting, refuting, detected: Utc::now() });
            if schisms.len() > 256 { let n = schisms.len()-256; schisms.drain(0..n); }
        }
    }
    pub async fn resolve_schism(&self, predicate: &str, winning_polarity: bool) -> bool {
        let mut schisms = self.schisms.write().await;
        let Some(idx) = schisms.iter().position(|s| s.predicate == predicate) else { return false };
        schisms.remove(idx); drop(schisms);
        let mut beliefs = self.beliefs.write().await;
        for b in beliefs.values_mut() { if b.predicate == predicate && b.polarity != winning_polarity { b.lodds = 0.0; } }
        true
    }
    pub async fn belief(&self, id:&str)->Option<Belief>{self.beliefs.read().await.get(id).cloned()}
    pub async fn schisms(&self)->Vec<Schism>{self.schisms.read().await.clone()}
    pub async fn stats(&self)->serde_json::Value{
        let beliefs=self.beliefs.read().await; let convinced=beliefs.values().filter(|b|b.lodds.abs()>WITNESS_STEP).count();
        serde_json::json!({"beliefs":beliefs.len(),"convinced":convinced,"open_schisms":self.schisms.read().await.len()})
    }
}
