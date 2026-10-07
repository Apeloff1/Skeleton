use std::collections::HashMap;
use chrono::{DateTime,Utc};
use serde::{Deserialize,Serialize};
use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug,Clone,Serialize,Deserialize)] pub struct Rule{pub id:String,pub action:String,pub min_weight:u32,pub requires_quorum:bool}
#[derive(Debug,Clone,Serialize,Deserialize)] pub struct Charter{pub id:String,pub domain:String,pub rules:Vec<Rule>,pub ratified:DateTime<Utc>,pub amendments:u32}
#[derive(Debug,Clone,Serialize,Deserialize)] pub struct Edict{pub id:String,pub charter_id:String,pub rule:Rule,pub proposed_by:String,pub proposed_at:DateTime<Utc>,pub in_force:bool}
#[derive(Debug,Clone,Serialize,Deserialize)] pub struct Decision{pub permitted:bool,pub cited_rule:Option<String>,pub reason:String}
pub struct Governance{charters:RwLock<HashMap<String,Charter>>,edicts:RwLock<HashMap<String,Edict>>}
impl Default for Governance{fn default()->Self{Self::new()}}
impl Governance{
 pub fn new()->Self{Self{charters:RwLock::new(HashMap::new()),edicts:RwLock::new(HashMap::new())}}
 pub async fn ratify(&self,domain:&str,rules:Vec<Rule>)->Charter{let c=Charter{id:Uuid::new_v4().to_string(),domain:domain.to_string(),rules,ratified:Utc::now(),amendments:0};self.charters.write().await.insert(c.domain.clone(),c.clone());c}
 pub async fn propose_edict(&self,domain:&str,rule:Rule,by:&str)->Option<String>{let c=self.charters.read().await;let charter=c.get(domain)?;let e=Edict{id:Uuid::new_v4().to_string(),charter_id:charter.id.clone(),rule,proposed_by:by.to_string(),proposed_at:Utc::now(),in_force:false};let p=format!("edict:{}",e.id);self.edicts.write().await.insert(e.id.clone(),e);Some(p)}
 pub async fn enforce_edict(&self,id:&str)->Option<()>{let mut es=self.edicts.write().await;let e=es.get_mut(id)?;if e.in_force{return Some(())}e.in_force=true;let cid=e.charter_id.clone();let rule=e.rule.clone();drop(es);let mut cs=self.charters.write().await;for c in cs.values_mut(){if c.id==cid{c.rules.push(rule);c.amendments+=1;break}}Some(())}
 pub async fn decide(&self,domain:&str,action:&str,actor_weight:u32)->Decision{let cs=self.charters.read().await;let Some(c)=cs.get(domain) else{return Decision{permitted:false,cited_rule:None,reason:format!("no charter ratified for domain '{domain}'")}};match c.rules.iter().find(|r|r.action==action){Some(r) if actor_weight>=r.min_weight=>Decision{permitted:true,cited_rule:Some(r.id.clone()),reason:if r.requires_quorum{"permitted by charter; quorum still required".into()}else{"permitted by charter".into()}},Some(r)=>Decision{permitted:false,cited_rule:Some(r.id.clone()),reason:format!("actor weight {actor_weight} below required {}",r.min_weight)},None=>Decision{permitted:false,cited_rule:None,reason:format!("action '{action}' not written into the {domain} charter")}}}
 pub async fn charters(&self)->Vec<Charter>{self.charters.read().await.values().cloned().collect()}
 pub async fn edicts(&self)->Vec<Edict>{self.edicts.read().await.values().cloned().collect()}
}
