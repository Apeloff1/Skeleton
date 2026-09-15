//! Mined from gameforge-rs and tightened for standalone workspace use.
//! Bounded cache, adaptive admission, buffer reuse, request coalescing,
//! health pooling, and progressive degradation.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{Mutex, Notify, Semaphore};

pub mod cache {
    use super::*;
    const L1_CAP: usize = 512;
    const L2_CAP: usize = 4096;
    const L1_TTL: Duration = Duration::from_secs(60);
    const L2_TTL: Duration = Duration::from_secs(300);

    struct Entry { value: Arc<serde_json::Value>, inserted: Instant, hits: u64 }
    pub struct TieredCache {
        l1: Mutex<HashMap<String, Entry>>, l2: Mutex<HashMap<String, Entry>>,
        l1_order: Mutex<Vec<String>>, l2_order: Mutex<Vec<String>>,
        pub hits: AtomicU64, pub misses: AtomicU64,
    }
    impl Default for TieredCache { fn default() -> Self { Self::new() } }
    impl TieredCache {
        pub fn new() -> Self { Self { l1: Mutex::new(HashMap::with_capacity(L1_CAP)), l2: Mutex::new(HashMap::with_capacity(L2_CAP)), l1_order: Mutex::new(Vec::with_capacity(L1_CAP)), l2_order: Mutex::new(Vec::with_capacity(L2_CAP)), hits: AtomicU64::new(0), misses: AtomicU64::new(0) } }
        pub async fn get(&self, key: &str) -> Option<Arc<serde_json::Value>> {
            if let Some(e) = self.l1.lock().await.get(key) { if e.inserted.elapsed() < L1_TTL { self.hits.fetch_add(1, Ordering::Relaxed); return Some(e.value.clone()); } }
            let mut l2 = self.l2.lock().await;
            if let Some(e) = l2.get_mut(key) { if e.inserted.elapsed() < L2_TTL { e.hits += 1; let v = e.value.clone(); let promote = e.hits >= 2; drop(l2); self.hits.fetch_add(1, Ordering::Relaxed); if promote { self.put_l1(key.to_string(), v.clone()).await; } return Some(v); } }
            drop(l2); self.misses.fetch_add(1, Ordering::Relaxed); None
        }
        pub async fn put(&self, key: String, value: serde_json::Value) { self.put_l2(key, Arc::new(value)).await; }
        async fn put_l1(&self, key: String, value: Arc<serde_json::Value>) {
            let mut map = self.l1.lock().await; let mut order = self.l1_order.lock().await;
            if map.len() >= L1_CAP && !map.contains_key(&key) { if let Some(victim) = order.first().cloned() { map.remove(&victim); order.remove(0); } }
            if !map.contains_key(&key) { order.push(key.clone()); }
            map.insert(key, Entry { value, inserted: Instant::now(), hits: 0 });
        }
        async fn put_l2(&self, key: String, value: Arc<serde_json::Value>) {
            let mut map = self.l2.lock().await; let mut order = self.l2_order.lock().await;
            if map.len() >= L2_CAP && !map.contains_key(&key) { if let Some(victim) = order.first().cloned() { map.remove(&victim); order.remove(0); } }
            if !map.contains_key(&key) { order.push(key.clone()); }
            map.insert(key, Entry { value, inserted: Instant::now(), hits: 0 });
        }
        pub async fn invalidate(&self, key: &str) { self.l1.lock().await.remove(key); self.l2.lock().await.remove(key); }
        pub async fn stats(&self) -> serde_json::Value { serde_json::json!({"l1_entries":self.l1.lock().await.len(),"l2_entries":self.l2.lock().await.len(),"hits":self.hits.load(Ordering::Relaxed),"misses":self.misses.load(Ordering::Relaxed)}) }
    }
}

pub mod backpressure {
    use super::*;
    pub struct AdaptiveGate { tokens: AtomicUsize, capacity: usize, refill_per_sec: usize, admitted: AtomicU64, shed: AtomicU64, last_refill: Mutex<Instant> }
    #[derive(Debug, Clone, Copy, PartialEq, Eq)] pub enum Verdict { Admitted, Shed }
    impl AdaptiveGate {
        pub fn new(capacity: usize, refill_per_sec: usize) -> Self { Self { tokens: AtomicUsize::new(capacity), capacity, refill_per_sec, admitted: AtomicU64::new(0), shed: AtomicU64::new(0), last_refill: Mutex::new(Instant::now()) } }
        async fn refill(&self) { let mut last = self.last_refill.lock().await; let elapsed = last.elapsed(); let add = (elapsed.as_secs_f64() * self.refill_per_sec as f64) as usize; if add > 0 { let cur = self.tokens.load(Ordering::Relaxed); self.tokens.store((cur + add).min(self.capacity), Ordering::Relaxed); *last = Instant::now(); } }
        pub async fn admit(&self, priority: u8) -> Verdict { self.refill().await; loop { let cur = self.tokens.load(Ordering::Relaxed); if cur == 0 && priority > 0 { self.shed.fetch_add(1, Ordering::Relaxed); return Verdict::Shed; } let next = cur.saturating_sub(1); if self.tokens.compare_exchange(cur, next, Ordering::Relaxed, Ordering::Relaxed).is_ok() { self.admitted.fetch_add(1, Ordering::Relaxed); return Verdict::Admitted; } } }
        pub fn stats(&self) -> serde_json::Value { serde_json::json!({"tokens_available":self.tokens.load(Ordering::Relaxed),"capacity":self.capacity,"admitted":self.admitted.load(Ordering::Relaxed),"shed":self.shed.load(Ordering::Relaxed)}) }
    }
    pub struct BackgroundLane { permits: Arc<Semaphore>, open: AtomicU64 }
    impl Default for BackgroundLane { fn default() -> Self { Self::new(4) } }
    impl BackgroundLane {
        pub fn new(max_concurrent: usize) -> Self { Self { permits: Arc::new(Semaphore::new(max_concurrent)), open: AtomicU64::new(0) } }
        pub fn try_enter(&self) -> Option<tokio::sync::OwnedSemaphorePermit> { match self.permits.clone().try_acquire_owned() { Ok(p) => { self.open.fetch_add(1, Ordering::Relaxed); Some(p) }, Err(_) => None } }
        pub fn open(&self) -> u64 { self.open.load(Ordering::Relaxed) }
    }
}

pub mod buffers {
    use super::*;
    pub struct BufferPool { small: Mutex<Vec<Vec<u8>>>, medium: Mutex<Vec<Vec<u8>>>, large: Mutex<Vec<Vec<u8>>>, pub leased: AtomicU64 }
    pub struct Lease { pub buf: Vec<u8>, class: Class, pool: Arc<BufferPool> }
    #[derive(Clone, Copy, PartialEq, Eq)] enum Class { Small, Medium, Large }
    const CLASS_CAP: usize = 64;
    impl Default for BufferPool { fn default() -> Self { Self::new() } }
    impl BufferPool {
        pub fn new() -> Self { Self { small: Mutex::new(Vec::with_capacity(CLASS_CAP)), medium: Mutex::new(Vec::with_capacity(CLASS_CAP)), large: Mutex::new(Vec::with_capacity(CLASS_CAP)), leased: AtomicU64::new(0) } }
        pub async fn lease(self: &Arc<Self>, min_size: usize) -> Lease { self.leased.fetch_add(1, Ordering::Relaxed); let (class, cap) = if min_size <= 4096 {(Class::Small,4096)} else if min_size <= 65536 {(Class::Medium,65536)} else {(Class::Large,1<<20)}; let buf = match class { Class::Small => self.small.lock().await.pop(), Class::Medium => self.medium.lock().await.pop(), Class::Large => self.large.lock().await.pop() }.unwrap_or_else(|| vec![0u8;cap]); Lease { buf, class, pool:self.clone() } }
        async fn reclaim(&self, class: Class, mut buf: Vec<u8>) { buf.clear(); self.leased.fetch_sub(1, Ordering::Relaxed); let lane = match class { Class::Small=>&self.small, Class::Medium=>&self.medium, Class::Large=>&self.large }; let mut lane=lane.lock().await; if lane.len()<CLASS_CAP { lane.push(buf); } }
    }
    impl Drop for Lease { fn drop(&mut self) { let pool=self.pool.clone(); let class=self.class; let buf=std::mem::take(&mut self.buf); if let Ok(handle)=tokio::runtime::Handle::try_current(){ handle.spawn(async move { pool.reclaim(class,buf).await; }); } } }
}

pub mod chaos {
    use super::*;
    #[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)] pub enum Rung { Normal=0, ReducedCaching=1, ShedBackground=2, StaleReads=3, EmergencyReadOnly=4 }
    impl Rung { pub fn name(&self)->&'static str { match self { Self::Normal=>"normal", Self::ReducedCaching=>"reduced_caching", Self::ShedBackground=>"shed_background", Self::StaleReads=>"stale_reads", Self::EmergencyReadOnly=>"emergency_read_only" } } }
    pub struct Governor { rung:AtomicUsize, window:Mutex<Vec<(Instant,bool)>>, window_span:Duration, escalate_at:f64, recover_at:f64, notify:Notify }
    impl Default for Governor { fn default()->Self{Self::new()} }
    impl Governor {
        pub fn new()->Self{Self{rung:AtomicUsize::new(0),window:Mutex::new(Vec::with_capacity(1024)),window_span:Duration::from_secs(30),escalate_at:0.25,recover_at:0.05,notify:Notify::new()}}
        pub fn rung(&self)->Rung{match self.rung.load(Ordering::Relaxed){0=>Rung::Normal,1=>Rung::ReducedCaching,2=>Rung::ShedBackground,3=>Rung::StaleReads,_=>Rung::EmergencyReadOnly}}
        pub async fn observe(&self,ok:bool){let mut w=self.window.lock().await;let now=Instant::now();w.push((now,ok));let cutoff=now-self.window_span;w.retain(|(t,_)|*t>cutoff);if w.len()<16{return}let errs=w.iter().filter(|(_,ok)|!*ok).count();let rate=errs as f64/w.len() as f64;let cur=self.rung.load(Ordering::Relaxed);if rate>self.escalate_at&&cur<4{self.rung.store(cur+1,Ordering::Relaxed);self.notify.notify_waiters();tracing::warn!(rung=cur+1,error_rate=rate,"chaos governor escalated");}else if rate<self.recover_at&&cur>0{self.rung.store(cur-1,Ordering::Relaxed);tracing::info!(rung=cur-1,error_rate=rate,"chaos governor recovered");}}
        pub fn permits_writes(&self)->bool{self.rung()<Rung::EmergencyReadOnly} pub fn permits_background(&self)->bool{self.rung()<Rung::ShedBackground} pub fn should_cache(&self)->bool{self.rung()<Rung::ReducedCaching}
        pub fn stats(&self)->serde_json::Value{serde_json::json!({"rung":self.rung().name(),"permits_writes":self.permits_writes(),"permits_background":self.permits_background()})}
    }
}

pub mod coalesce {
    use super::*; use tokio::sync::broadcast;
    pub struct Coalescer<F,Fut> where F:Fn(String)->Fut+Send+Sync+'static,Fut:std::future::Future<Output=anyhow::Result<serde_json::Value>>+Send+'static { fetch:F, in_flight:Mutex<HashMap<String,broadcast::Sender<Arc<serde_json::Value>>>> }
    impl<F,Fut> Coalescer<F,Fut> where F:Fn(String)->Fut+Send+Sync+'static,Fut:std::future::Future<Output=anyhow::Result<serde_json::Value>>+Send+'static {
        pub fn new(fetch:F)->Self{Self{fetch,in_flight:Mutex::new(HashMap::new())}}
        pub async fn get(&self,key:String)->anyhow::Result<Arc<serde_json::Value>>{let mut map=self.in_flight.lock().await;if let Some(tx)=map.get(&key){let mut rx=tx.subscribe();drop(map);return rx.recv().await.map_err(|_|anyhow::anyhow!("coalesced fetch failed"));}let(tx,_)=broadcast::channel(1);map.insert(key.clone(),tx);drop(map);let result=(self.fetch)(key.clone()).await;let mut map=self.in_flight.lock().await;if let Some(tx)=map.remove(&key){if let Ok(v)=&result{let _=tx.send(Arc::new(v.clone()));}}result.map(Arc::new)}
    }
}

pub mod pool {
    use super::*;
    pub struct HealthPool<T:Send+'static>{make:Arc<dyn Fn()->T+Send+Sync>,check:Arc<dyn Fn(&T)->bool+Send+Sync>,idle:Mutex<Vec<(T,Instant)>>,max_age:Duration,cap:usize,pub checkouts:AtomicU64,pub replaced:AtomicU64}
    impl<T:Send+'static> HealthPool<T>{pub fn new(cap:usize,max_age:Duration,make:impl Fn()->T+Send+Sync+'static,check:impl Fn(&T)->bool+Send+Sync+'static)->Self{Self{make:Arc::new(make),check:Arc::new(check),idle:Mutex::new(Vec::with_capacity(cap)),max_age,cap,checkouts:AtomicU64::new(0),replaced:AtomicU64::new(0)}}pub async fn checkout(&self)->T{self.checkouts.fetch_add(1,Ordering::Relaxed);let mut idle=self.idle.lock().await;while let Some((conn,born))=idle.pop(){if born.elapsed()<self.max_age&&(self.check)(&conn){return conn}self.replaced.fetch_add(1,Ordering::Relaxed);}drop(idle);(self.make)()}pub async fn checkin(&self,conn:T){let mut idle=self.idle.lock().await;if idle.len()<self.cap{idle.push((conn,Instant::now()));}}pub fn stats(&self)->serde_json::Value{serde_json::json!({"checkouts":self.checkouts.load(Ordering::Relaxed),"replaced":self.replaced.load(Ordering::Relaxed)})}}
}

pub mod prelude { pub use super::backpressure::{AdaptiveGate,BackgroundLane,Verdict}; pub use super::buffers::BufferPool; pub use super::cache::TieredCache; pub use super::chaos::{Governor,Rung}; pub use super::coalesce::Coalescer; pub use super::pool::HealthPool; }
