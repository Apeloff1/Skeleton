use std::sync::Arc;
use axum::{extract::{Path, State}, http::{HeaderMap, StatusCode}, response::IntoResponse, routing::{get, post}, Json, Router};
use serde::{Deserialize, Serialize};
use tower_http::request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer};
use tower_http::trace::TraceLayer;
use gf_services::prelude::*;

pub mod seal;

pub mod state {
    use super::*;
    #[derive(Clone)]
    pub struct AppState {
        pub zaibatsu: gf_gameforge::SharedZaibatsu,
        pub cache: Arc<TieredCache>,
        pub gate: Arc<AdaptiveGate>,
        pub governor: Arc<Governor>,
        pub buffers: Arc<BufferPool>,
        pub background: Arc<BackgroundLane>,
        pub started: std::time::Instant,
    }
    impl AppState { pub fn new() -> Self { Self { zaibatsu: Arc::new(gf_gameforge::Zaibatsu::new()), cache: Arc::new(TieredCache::new()), gate: Arc::new(AdaptiveGate::new(2048, 1024)), governor: Arc::new(Governor::new()), buffers: Arc::new(BufferPool::new()), background: Arc::new(BackgroundLane::new(4)), started: std::time::Instant::now() } } }
    impl Default for AppState { fn default() -> Self { Self::new() } }
}
use state::AppState;

#[derive(Serialize)] struct Health { status: &'static str, version: &'static str, uptime_secs: u64, chaos: serde_json::Value }
async fn health(State(s): State<AppState>) -> impl IntoResponse {
    let rung=s.governor.rung(); let status=if rung==Rung::EmergencyReadOnly{"degraded"}else{"ok"}; let code=if status=="ok"{StatusCode::OK}else{StatusCode::SERVICE_UNAVAILABLE};
    (code,Json(Health{status,version:env!("CARGO_PKG_VERSION"),uptime_secs:s.started.elapsed().as_secs(),chaos:s.governor.stats()}))
}
async fn ready(State(s): State<AppState>) -> impl IntoResponse {
    match gf_core::db::get_db().await { Ok(db)=>{let ok=db.run_command(gf_core::doc!{"ping":1}).await.is_ok();s.governor.observe(ok).await;if ok{(StatusCode::OK,Json(serde_json::json!({"ready":true})))}else{(StatusCode::SERVICE_UNAVAILABLE,Json(serde_json::json!({"ready":false,"mongo":"unreachable"})))}} Err(_)=>{s.governor.observe(false).await;(StatusCode::SERVICE_UNAVAILABLE,Json(serde_json::json!({"ready":false})))} }
}
async fn infra_stats(State(s): State<AppState>) -> impl IntoResponse { Json(serde_json::json!({"cache":s.cache.stats().await,"backpressure":s.gate.stats(),"chaos":s.governor.stats(),"delta_memory":s.zaibatsu.delta.stats().await,"fabric_seq":s.zaibatsu.fabric.current_seq().await,"fabric_head_hash":s.zaibatsu.fabric.head_hash().await,"cognition":s.zaibatsu.cognition.stats().await,"lafs":s.zaibatsu.lafs.stats().await,"swarm":s.zaibatsu.swarm.stats().await,"outbox_pending":s.zaibatsu.fabric.outbox().pending_count().await,"background_open":s.background.open()})) }
async fn verify_chain(State(s): State<AppState>) -> impl IntoResponse { match s.zaibatsu.fabric.verify_chain().await { Ok(())=>(StatusCode::OK,Json(serde_json::json!({"chain":"intact"}))).into_response(), Err((seq,why))=>(StatusCode::CONFLICT,Json(serde_json::json!({"chain":"broken","at_seq":seq,"evidence":why}))).into_response() } }

async fn admit_write(s:&AppState,headers:&HeaderMap)->Result<String,axum::response::Response>{let attester=seal::require_seal(headers)?;match s.gate.admit(1).await{Verdict::Shed=>{s.governor.observe(false).await;Err((StatusCode::TOO_MANY_REQUESTS,Json(serde_json::json!({"error":"shed"}))).into_response())},Verdict::Admitted=>{if !s.governor.permits_writes(){return Err((StatusCode::SERVICE_UNAVAILABLE,Json(serde_json::json!({"error":"emergency_read_only"}))).into_response())}Ok(attester)}}}

#[derive(Deserialize)] struct MintBody{attester:String,#[serde(default="default_ttl")]ttl_secs:u64} fn default_ttl()->u64{3600}
async fn mint(headers:HeaderMap,Json(body):Json<MintBody>)->impl IntoResponse{let operator=std::env::var("GF_OPERATOR_KEY").unwrap_or_default();let given=headers.get("x-gf-operator").and_then(|v|v.to_str().ok()).unwrap_or("");if operator.is_empty()||given!=operator{return(StatusCode::UNAUTHORIZED,Json(serde_json::json!({"error":"operator key required"}))).into_response()}match seal::mint_seal(&body.attester,body.ttl_secs){Some(s)=>(StatusCode::OK,Json(serde_json::json!({"seal":s}))).into_response(),None=>(StatusCode::SERVICE_UNAVAILABLE,Json(serde_json::json!({"error":"seal secret not configured"}))).into_response()}}

#[derive(Deserialize)] struct ProposeBody{ledger:String,kind:String,proposal_id:String,value:serde_json::Value}
async fn propose(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<ProposeBody>)->axum::response::Response{let attester=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};let(verdict,ev)=s.zaibatsu.propose(&body.ledger,&body.kind,&body.proposal_id,&attester,body.value).await;let resp=serde_json::json!({"verdict":format!("{:?}",verdict).to_lowercase(),"event_id":ev.as_ref().map(|e|e.id.clone()),"seq":ev.as_ref().map(|e|e.seq),"hash":ev.as_ref().map(|e|e.hash.clone())});s.governor.observe(true).await;(StatusCode::OK,Json(resp)).into_response()}
async fn fabric_tail(State(s):State<AppState>,Path(ledger):Path<String>)->impl IntoResponse{Json(s.zaibatsu.fabric.tail(&ledger,128).await)}
async fn court_suspects(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.court.suspects().await)}
async fn list_sagas(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.sagas.list().await)}

#[derive(Deserialize)] struct FoundLegionBody{name:String,motto:String}
async fn found_legion(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<FoundLegionBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let l=s.zaibatsu.legions.found(&body.name,&body.motto).await;s.governor.observe(true).await;(StatusCode::CREATED,Json(serde_json::to_value(l).unwrap())).into_response()}
#[derive(Deserialize)] struct EnlistBody{capability:String}
async fn enlist(State(s):State<AppState>,headers:HeaderMap,Path(name):Path<String>,Json(body):Json<EnlistBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.legions.enlist(&name,&body.capability).await{Some(id)=>(StatusCode::CREATED,Json(serde_json::json!({"member_id":id}))).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no such legion"}))).into_response()}}
async fn list_legions(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.legions.list().await)}
#[derive(Deserialize)] struct HeartbeatBody{member_id:String}
async fn heartbeat(State(s):State<AppState>,headers:HeaderMap,Path(name):Path<String>,Json(body):Json<HeartbeatBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let ok=s.zaibatsu.legions.heartbeat(&name,&body.member_id).await;(if ok{StatusCode::OK}else{StatusCode::NOT_FOUND},Json(serde_json::json!({"alive":ok}))).into_response()}
#[derive(Deserialize)] struct CashierBody{member_id:String}
async fn cashier(State(s):State<AppState>,headers:HeaderMap,Path(name):Path<String>,Json(body):Json<CashierBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let ok=s.zaibatsu.legions.cashier(&name,&body.member_id).await;if ok{s.zaibatsu.reputation.record(&body.member_id,gf_gameforge::reputation::DeedKind::Treason,1.0).await;}(if ok{StatusCode::OK}else{StatusCode::NOT_FOUND},Json(serde_json::json!({"cashiered":ok}))).into_response()}
async fn fit_for(State(s):State<AppState>,Path(capability):Path<String>)->impl IntoResponse{Json(s.zaibatsu.legions.fit_for(&capability).await)}

#[derive(Deserialize)] struct SubmitTaskBody{id:String,capability:String,payload:serde_json::Value,#[serde(default)]deps:Vec<String>}
async fn submit_task(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<SubmitTaskBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.swarm.submit(&body.id,&body.capability,body.payload,body.deps).await{Ok(())=>(StatusCode::CREATED,Json(serde_json::json!({"submitted":body.id}))).into_response(),Err(e)=>(StatusCode::CONFLICT,Json(serde_json::json!({"error":format!("{e:?}")}))).into_response()}}
async fn ready_wave(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.swarm.ready_wave().await)}
#[derive(Deserialize)] struct ClaimBody{executor:String}
async fn claim_task(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>,Json(body):Json<ClaimBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.swarm.claim(&id,&body.executor).await{Some(t)=>(StatusCode::OK,Json(serde_json::to_value(t).unwrap())).into_response(),None=>(StatusCode::CONFLICT,Json(serde_json::json!({"error":"not claimable"}))).into_response()}}
#[derive(Deserialize)] struct CompleteBody{result:serde_json::Value}
async fn complete_task(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>,Json(body):Json<CompleteBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};match s.zaibatsu.swarm.complete(&id,body.result).await{Some(())=>{s.zaibatsu.reputation.record(&a,gf_gameforge::reputation::DeedKind::Service,0.6).await;(StatusCode::OK,Json(serde_json::json!({"done":id}))).into_response()},None=>(StatusCode::CONFLICT,Json(serde_json::json!({"error":"not running"}))).into_response()}}
async fn swarm_stats(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.swarm.stats().await)}

#[derive(Deserialize)] struct RatifyBody{domain:String,rules:Vec<gf_gameforge::governance::Rule>}
async fn ratify_charter(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<RatifyBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let c=s.zaibatsu.governance.ratify(&body.domain,body.rules).await;(StatusCode::CREATED,Json(serde_json::to_value(c).unwrap())).into_response()}
async fn list_charters(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.governance.charters().await)}
#[derive(Deserialize)] struct DecideBody{domain:String,action:String,#[serde(default)]actor_weight:u32}
async fn decide(State(s):State<AppState>,Json(body):Json<DecideBody>)->impl IntoResponse{Json(s.zaibatsu.governance.decide(&body.domain,&body.action,body.actor_weight).await)}
#[derive(Deserialize)] struct ProposeEdictBody{domain:String,rule:gf_gameforge::governance::Rule}
async fn propose_edict(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<ProposeEdictBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};match s.zaibatsu.governance.propose_edict(&body.domain,body.rule,&a).await{Some(p)=>(StatusCode::ACCEPTED,Json(serde_json::json!({"proposal_id":p}))).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no charter for domain"}))).into_response()}}
async fn list_edicts(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.governance.edicts().await)}

#[derive(Deserialize)] struct HoldBody{predicate:String,polarity:bool}
async fn hold_belief(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<HoldBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let id=s.zaibatsu.cognition.hold(&body.predicate,body.polarity).await;(StatusCode::CREATED,Json(serde_json::json!({"belief_id":id}))).into_response()}
#[derive(Deserialize)] struct TestifyBody{supports:bool,#[serde(default="half_weight")]weight:f64}fn half_weight()->f64{0.5}
async fn testify(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>,Json(body):Json<TestifyBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};match s.zaibatsu.cognition.testify(&id,&a,body.supports,body.weight).await{Some(c)=>(StatusCode::OK,Json(serde_json::json!({"confidence":c}))).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no such belief"}))).into_response()}}
async fn schisms(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.cognition.schisms().await)}
#[derive(Deserialize)] struct ResolveBody{predicate:String,winning_polarity:bool}
async fn resolve_schism(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<ResolveBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};let ok=s.zaibatsu.cognition.resolve_schism(&body.predicate,body.winning_polarity).await;if ok{s.zaibatsu.reputation.record(&a,gf_gameforge::reputation::DeedKind::Distinction,0.8).await;}(if ok{StatusCode::OK}else{StatusCode::NOT_FOUND},Json(serde_json::json!({"resolved":ok}))).into_response()}

#[derive(Deserialize)] struct PutChunkBody{data_b64:String}
fn b64_decode(s:&str)->Option<Vec<u8>>{const T:[i8;256]={let mut t=[-1i8;256];let mut i=0;while i<26{t[b'A' as usize+i]=i as i8;t[b'a' as usize+i]=(i+26)as i8;i+=1;}let mut d=0;while d<10{t[b'0' as usize+d]=(d+52)as i8;d+=1;}t[b'+' as usize]=62;t[b'/' as usize]=63;t};let mut out=Vec::with_capacity(s.len()*3/4);let mut acc=0u32;let mut nbits=0u32;for &b in s.as_bytes(){if b==b'='||b==b'\n'||b==b'\r'{continue}let v=T[b as usize];if v<0{return None}acc=(acc<<6)|v as u32;nbits+=6;if nbits>=8{nbits-=8;out.push((acc>>nbits)as u8);}}Some(out)}
fn b64_encode(data:&[u8])->String{const A:&[u8;64]=b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";let mut out=String::with_capacity(data.len()*4/3+4);for chunk in data.chunks(3){let b0=chunk[0]as u32;let b1=chunk.get(1).copied().unwrap_or(0)as u32;let b2=chunk.get(2).copied().unwrap_or(0)as u32;let n=(b0<<16)|(b1<<8)|b2;out.push(A[(n>>18)as usize&63]as char);out.push(A[(n>>12)as usize&63]as char);if chunk.len()>1{out.push(A[(n>>6)as usize&63]as char)}else{out.push('=')}if chunk.len()>2{out.push(A[n as usize&63]as char)}else{out.push('=')}}out}
async fn put_chunk(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<PutChunkBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let bytes=match b64_decode(&body.data_b64){Some(b)=>b,None=>return(StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":"invalid base64"}))).into_response()};match s.zaibatsu.lafs.put_chunk(&bytes).await{Ok(d)=>(StatusCode::CREATED,Json(serde_json::json!({"digest":d}))).into_response(),Err(e)=>(StatusCode::PAYLOAD_TOO_LARGE,Json(serde_json::json!({"error":e}))).into_response()}}
async fn get_chunk(State(s):State<AppState>,Path(digest):Path<String>)->axum::response::Response{match s.zaibatsu.lafs.get_chunk(&digest).await{Some(c)=>(StatusCode::OK,Json(serde_json::json!({"digest":c.digest,"bytes":c.bytes.len(),"data_b64":b64_encode(&c.bytes)}))).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"unknown chunk"}))).into_response()}}
#[derive(Deserialize)] struct PinBody{name:String,chunks:Vec<String>}
async fn pin_manifest(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<PinBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.lafs.pin_manifest(&body.name,body.chunks).await{Ok(m)=>(StatusCode::CREATED,Json(serde_json::to_value(m).unwrap())).into_response(),Err(e)=>(StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":e}))).into_response()}}
async fn read_manifest(State(s):State<AppState>,Path(name):Path<String>)->axum::response::Response{match s.zaibatsu.lafs.read_manifest(&name).await{Some(bytes)=>(StatusCode::OK,Json(serde_json::json!({"name":name,"bytes":bytes.len(),"data_b64":b64_encode(&bytes)}))).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"unknown or corrupt manifest"}))).into_response()}}
async fn list_manifests(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.lafs.manifests().await)}

#[derive(Deserialize)] struct SubmitJobBody{asset:String,pipeline:Vec<String>}
async fn submit_job(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<SubmitJobBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let stages:Vec<&str>=body.pipeline.iter().map(|x|x.as_str()).collect();let j=s.zaibatsu.studio.submit(&s.zaibatsu.sagas,&body.asset,stages).await;(StatusCode::CREATED,Json(serde_json::to_value(j).unwrap())).into_response()}
async fn advance_job(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.studio.advance(&s.zaibatsu.sagas,&id).await{Some(j)=>(StatusCode::OK,Json(serde_json::to_value(j).unwrap())).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no such job"}))).into_response()}}
async fn fail_job(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.studio.fail(&s.zaibatsu.sagas,&id).await{Some(j)=>(StatusCode::OK,Json(serde_json::to_value(j).unwrap())).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no such job"}))).into_response()}}
#[derive(Deserialize)] struct PublishBody{output_manifest:String}
async fn publish_job(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>,Json(body):Json<PublishBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.studio.publish(&id,&body.output_manifest).await{Some(j)=>(StatusCode::OK,Json(serde_json::to_value(j).unwrap())).into_response(),None=>(StatusCode::CONFLICT,Json(serde_json::json!({"error":"not done or unknown"}))).into_response()}}
async fn list_jobs(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.studio.list().await)}

#[derive(Deserialize)] struct ConveneBody{title:String,agenda:Vec<String>}
async fn convene(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<ConveneBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};let session=s.zaibatsu.boardroom.convene(&body.title,&a,body.agenda).await;(StatusCode::CREATED,Json(serde_json::to_value(session).unwrap())).into_response()}
#[derive(Deserialize)] struct MotionBody{text:String}
async fn table_motion(State(s):State<AppState>,headers:HeaderMap,Path(session):Path<String>,Json(body):Json<MotionBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};match s.zaibatsu.boardroom.table_motion(&session,&a,&body.text).await{Some((m,p))=>(StatusCode::ACCEPTED,Json(serde_json::json!({"motion":m,"court_proposal_id":p}))).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no open session"}))).into_response()}}
#[derive(Deserialize)] struct ResolveMotionBody{carried:bool,event_id:Option<String>}
async fn resolve_motion(State(s):State<AppState>,headers:HeaderMap,Path(motion):Path<String>,Json(body):Json<ResolveMotionBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.boardroom.resolve_motion(&motion,body.carried,body.event_id).await{Some(m)=>(StatusCode::OK,Json(serde_json::to_value(m).unwrap())).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no tabled motion"}))).into_response()}}
async fn adjourn(State(s):State<AppState>,headers:HeaderMap,Path(session):Path<String>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.boardroom.adjourn(&session).await{Some(x)=>(StatusCode::OK,Json(serde_json::to_value(x).unwrap())).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no open session"}))).into_response()}}
async fn board_sessions(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.boardroom.sessions().await)}

#[derive(Deserialize)] struct OpenAccountBody{name:String}
async fn open_account(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<OpenAccountBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let a=s.zaibatsu.economy.open_account(&body.name).await;(StatusCode::CREATED,Json(serde_json::to_value(a).unwrap())).into_response()}
#[derive(Deserialize)] struct MintBody2{account:String,amount:i64,provenance_event:String,#[serde(default)]memo:String}
async fn mint_scrip(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<MintBody2>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.economy.mint(&body.account,body.amount,&body.provenance_event,&body.memo).await{Ok(e)=>(StatusCode::CREATED,Json(serde_json::to_value(e).unwrap())).into_response(),Err(e)=>(StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":e}))).into_response()}}
#[derive(Deserialize)] struct TransferBody{from:String,to:String,amount:i64,#[serde(default)]memo:String}
async fn transfer(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<TransferBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}match s.zaibatsu.economy.transfer(&body.from,&body.to,body.amount,&body.memo).await{Ok((d,c))=>(StatusCode::CREATED,Json(serde_json::json!({"debit":d,"credit":c}))).into_response(),Err(e)=>(StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":e}))).into_response()}}
#[derive(Deserialize)] struct FreezeBody{frozen:bool}
async fn freeze_account(State(s):State<AppState>,headers:HeaderMap,Path(account):Path<String>,Json(body):Json<FreezeBody>)->axum::response::Response{if let Err(r)=admit_write(&s,&headers).await{return r}let ok=s.zaibatsu.economy.freeze(&account,body.frozen).await;(if ok{StatusCode::OK}else{StatusCode::NOT_FOUND},Json(serde_json::json!({"frozen":ok}))).into_response()}
async fn treasury_audit(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.economy.audit().await)}
async fn standing(State(s):State<AppState>,Path(actor):Path<String>)->impl IntoResponse{Json(serde_json::json!({"actor":actor,"standing":s.zaibatsu.reputation.standing(&actor).await}))}
async fn honor_roll(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.reputation.roll().await)}

#[derive(Deserialize)] struct ProposeMeasureBody{title:String,options:Vec<String>,#[serde(default="default_open_secs")]open_secs:i64}fn default_open_secs()->i64{86400}
async fn propose_measure(State(s):State<AppState>,headers:HeaderMap,Json(body):Json<ProposeMeasureBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};match s.zaibatsu.voting.propose(&body.title,body.options,&a,body.open_secs).await{Ok(m)=>(StatusCode::CREATED,Json(serde_json::to_value(m).unwrap())).into_response(),Err(e)=>(StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":e}))).into_response()}}
#[derive(Deserialize)] struct CastBody{option:String}
async fn cast_ballot(State(s):State<AppState>,headers:HeaderMap,Path(id):Path<String>,Json(body):Json<CastBody>)->axum::response::Response{let a=match admit_write(&s,&headers).await{Ok(a)=>a,Err(r)=>return r};match s.zaibatsu.voting.cast(&id,&a,&body.option).await{Ok(())=>(StatusCode::CREATED,Json(serde_json::json!({"cast":true}))).into_response(),Err(e)=>(StatusCode::CONFLICT,Json(serde_json::json!({"error":e}))).into_response()}}
async fn tally(State(s):State<AppState>,Path(id):Path<String>)->axum::response::Response{match s.zaibatsu.voting.tally(&id).await{Some(t)=>(StatusCode::OK,Json(t)).into_response(),None=>(StatusCode::NOT_FOUND,Json(serde_json::json!({"error":"no such measure"}))).into_response()}}
async fn measures(State(s):State<AppState>)->impl IntoResponse{Json(s.zaibatsu.voting.measures().await)}

pub fn build_router(state:AppState)->Router{
 let fabric=Router::new().route("/propose",post(propose)).route("/{ledger}/tail",get(fabric_tail)).route("/verify-chain",get(verify_chain));
 let legions=Router::new().route("/found",post(found_legion)).route("/list",get(list_legions)).route("/fit/{capability}",get(fit_for)).route("/{name}/enlist",post(enlist)).route("/{name}/heartbeat",post(heartbeat)).route("/{name}/cashier",post(cashier));
 let swarm=Router::new().route("/submit",post(submit_task)).route("/wave",get(ready_wave)).route("/stats",get(swarm_stats)).route("/{id}/claim",post(claim_task)).route("/{id}/complete",post(complete_task));
 let governance=Router::new().route("/charter",post(ratify_charter)).route("/charters",get(list_charters)).route("/decide",post(decide)).route("/edict",post(propose_edict)).route("/edicts",get(list_edicts));
 let cognition=Router::new().route("/hold",post(hold_belief)).route("/testify/{id}",post(testify)).route("/schisms",get(schisms)).route("/resolve",post(resolve_schism));
 let lafs=Router::new().route("/chunk",post(put_chunk)).route("/chunk/{digest}",get(get_chunk)).route("/manifest",post(pin_manifest)).route("/manifest/{name}",get(read_manifest)).route("/manifests",get(list_manifests));
 let studio=Router::new().route("/jobs",get(list_jobs)).route("/submit",post(submit_job)).route("/{id}/advance",post(advance_job)).route("/{id}/fail",post(fail_job)).route("/{id}/publish",post(publish_job));
 let boardroom=Router::new().route("/convene",post(convene)).route("/sessions",get(board_sessions)).route("/{session}/motion",post(table_motion)).route("/{session}/adjourn",post(adjourn)).route("/motion/{motion}/resolve",post(resolve_motion));
 let treasury=Router::new().route("/open",post(open_account)).route("/mint",post(mint_scrip)).route("/transfer",post(transfer)).route("/audit",get(treasury_audit)).route("/{account}/freeze",post(freeze_account));
 let reputation=Router::new().route("/roll",get(honor_roll)).route("/{actor}",get(standing));
 let diet=Router::new().route("/propose",post(propose_measure)).route("/measures",get(measures)).route("/{id}/cast",post(cast_ballot)).route("/{id}/tally",get(tally));
 let api=Router::new().route("/mint",post(mint)).route("/sagas",get(list_sagas)).route("/court/suspects",get(court_suspects)).route("/infra",get(infra_stats)).nest("/fabric",fabric).nest("/legions",legions).nest("/swarm",swarm).nest("/governance",governance).nest("/cognition",cognition).nest("/lafs",lafs).nest("/studio",studio).nest("/boardroom",boardroom).nest("/treasury",treasury).nest("/reputation",reputation).nest("/diet",diet);
 Router::new().route("/health",get(health)).route("/ready",get(ready)).nest("/api",api).with_state(state).layer(PropagateRequestIdLayer::x_request_id()).layer(TraceLayer::new_for_http()).layer(SetRequestIdLayer::x_request_id(MakeRequestUuid))
}

pub async fn serve()->anyhow::Result<()>{gf_core::structured_log::install_json_adapter();let settings=gf_core::settings::get_settings()?;let state=AppState::new();gf_core::outbox::spawn_reconciler(state.zaibatsu.fabric.outbox(),std::time::Duration::from_secs(5));let app=build_router(state);let addr=format!("0.0.0.0:{}",settings.port);let listener=tokio::net::TcpListener::bind(&addr).await?;tracing::info!(addr,"gf-server listening");axum::serve(listener,app).with_graceful_shutdown(shutdown_signal()).await?;Ok(())}
async fn shutdown_signal(){let _=tokio::signal::ctrl_c().await;tracing::info!("shutdown signal received — draining");}
