use std::collections::HashMap;
use chrono::{DateTime,Utc};
use serde::{Deserialize,Serialize};
use tokio::sync::RwLock;
use gf_core::digest::sha256_hex;
pub const CHUNK_CAP:usize=16384;pub const CHUNK_MAX_BYTES:usize=1<<20;
#[derive(Debug,Clone,Serialize,Deserialize)]pub struct Chunk{pub digest:String,pub bytes:Vec<u8>,pub stored:DateTime<Utc>}
#[derive(Debug,Clone,Serialize,Deserialize)]pub struct Manifest{pub id:String,pub name:String,pub chunks:Vec<String>,pub total_bytes:u64,pub created:DateTime<Utc>}
pub struct Lafs{chunks:RwLock<HashMap<String,Chunk>>,manifests:RwLock<HashMap<String,Manifest>>}
impl Default for Lafs{fn default()->Self{Self::new()}}
impl Lafs{
 pub fn new()->Self{Self{chunks:RwLock::new(HashMap::new()),manifests:RwLock::new(HashMap::new())}}
 pub async fn put_chunk(&self,bytes:&[u8])->Result<String,&'static str>{if bytes.len()>CHUNK_MAX_BYTES{return Err("chunk exceeds 1 MiB")}let digest=sha256_hex(bytes);let mut chunks=self.chunks.write().await;if chunks.contains_key(&digest){return Ok(digest)}if chunks.len()>=CHUNK_CAP{return Err("chunk store at capacity — compact before writing")}let chunk=Chunk{digest:digest.clone(),bytes:bytes.to_vec(),stored:Utc::now()};chunks.insert(digest.clone(),chunk.clone());drop(chunks);if let Ok(db)=gf_core::db::get_db().await{tokio::spawn(async move{let _=db.collection::<Chunk>("lafs_chunks").insert_one(chunk).await;});}Ok(digest)}
 pub async fn get_chunk(&self,d:&str)->Option<Chunk>{self.chunks.read().await.get(d).cloned()}
 pub async fn pin_manifest(&self,name:&str,digests:Vec<String>)->Result<Manifest,String>{let chunks=self.chunks.read().await;let mut total=0u64;for d in &digests{match chunks.get(d){Some(c)=>total+=c.bytes.len() as u64,None=>return Err(format!("unknown chunk {d}"))}}drop(chunks);let m=Manifest{id:uuid::Uuid::new_v4().to_string(),name:name.to_string(),chunks:digests,total_bytes:total,created:Utc::now()};self.manifests.write().await.insert(m.name.clone(),m.clone());Ok(m)}
 pub async fn read_manifest(&self,name:&str)->Option<Vec<u8>>{let m=self.manifests.read().await.get(name)?.clone();let chunks=self.chunks.read().await;let mut out=Vec::with_capacity(m.total_bytes as usize);for d in &m.chunks{let c=chunks.get(d)?;if sha256_hex(&c.bytes)!=*d{return None}out.extend_from_slice(&c.bytes)}Some(out)}
 pub async fn manifests(&self)->Vec<Manifest>{self.manifests.read().await.values().cloned().collect()}
 pub async fn stats(&self)->serde_json::Value{let c=self.chunks.read().await;let bytes:usize=c.values().map(|x|x.bytes.len()).sum();serde_json::json!({"chunks":c.len(),"bytes":bytes,"manifests":self.manifests.read().await.len()})}
}
