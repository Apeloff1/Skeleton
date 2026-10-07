//! gf-core v3.1 — Foundation crate. Settings, MongoDB async facade,
//! structured JSON logging, idempotency primitives, optimistic concurrency,
//! and the shared digest contract.
//!
//! v3.1 government-audit fixes:
//! - F2: idempotency matched on typed duplicate-key errors, never strings
//! - F6: sha2/hex pinned for the empire-wide digest contract
//! - get_sync_db removed: a sync facade that block_on's inside the runtime
//!   is a deadlock with a good suit on. Async spine, async only.

use std::sync::Arc;
use tokio::sync::RwLock;

/// The empire's single digest contract (F1): SHA-256, hex-encoded.
/// Quorum verdicts, LAFS addresses, and fabric hash-chains all answer to
/// this one function — no court rolls its own crypto.
pub mod digest {
    use sha2::{Digest, Sha256};

    pub fn sha256_hex(bytes: &[u8]) -> String {
        let mut h = Sha256::new();
        h.update(bytes);
        hex::encode(h.finalize())
    }
}

pub mod settings {
    use std::sync::OnceLock;
    use serde::Deserialize;

    #[derive(Debug, Clone, Deserialize)]
    pub struct Settings {
        #[serde(default = "default_port")]
        pub port: u16,
        #[serde(default = "default_mongo_url")]
        pub mongo_url: String,
        #[serde(default = "default_db_name")]
        pub db_name: String,
        #[serde(default = "default_fabric_persist")]
        pub fabric_persist_enabled: bool,
        #[serde(default = "default_log_format")]
        pub log_format: String,
        #[serde(default = "default_max_connections")]
        pub max_mongo_connections: u32,
    }

    fn default_port() -> u16 { 8001 }
    fn default_mongo_url() -> String { "mongodb://localhost:27017".into() }
    fn default_db_name() -> String { "gameforge".into() }
    fn default_fabric_persist() -> bool { true }
    fn default_log_format() -> String { "json".into() }
    fn default_max_connections() -> u32 { 100 }

    static SETTINGS: OnceLock<Settings> = OnceLock::new();

    pub fn get_settings() -> anyhow::Result<&'static Settings> {
        if let Some(s) = SETTINGS.get() { return Ok(s); }
        let s: Settings = config::Config::builder()
            .add_source(config::Environment::with_prefix("GF").separator("__"))
            .add_source(config::File::with_name("gameforge").required(false))
            .build()?
            .try_deserialize()
            .unwrap_or(Settings {
                port: default_port(),
                mongo_url: default_mongo_url(),
                db_name: default_db_name(),
                fabric_persist_enabled: default_fabric_persist(),
                log_format: default_log_format(),
                max_mongo_connections: default_max_connections(),
            });
        Ok(SETTINGS.get_or_init(|| s))
    }
}

pub mod db {
    use mongodb::{Client, Database, options::ClientOptions};
    use std::sync::Arc;
    use tokio::sync::OnceCell;

    static CLIENT: OnceCell<Arc<Client>> = OnceCell::const_new();

    pub async fn get_client() -> anyhow::Result<Arc<Client>> {
        CLIENT.get_or_try_init(|| async {
            let settings = crate::settings::get_settings()?;
            let mut opts = ClientOptions::parse(&settings.mongo_url).await?;
            opts.max_pool_size = Some(settings.max_mongo_connections);
            opts.min_pool_size = Some(10);
            opts.max_idle_time = Some(std::time::Duration::from_secs(300));
            opts.wait_queue_timeout = Some(std::time::Duration::from_secs(5));
            let client = Client::with_options(opts)?;
            Ok(Arc::new(client))
        }).await.cloned()
    }

    pub async fn get_db() -> anyhow::Result<Database> {
        let client = get_client().await?;
        let settings = crate::settings::get_settings()?;
        Ok(client.database(&settings.db_name))
    }
}

pub mod structured_log {
    use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

    pub fn install_json_adapter() {
        let filter = EnvFilter::from_default_env();
        let fmt = tracing_subscriber::fmt::layer().json().with_current_span(true);
        tracing_subscriber::registry().with(filter).with(fmt).init();
    }
}

pub mod guard {
    use mongodb::bson::{doc, Document};
    use mongodb::error::{ErrorKind, WriteFailure};
    use mongodb::Collection;

    fn is_duplicate_key(e: &mongodb::error::Error) -> bool {
        matches!(
            e.kind.as_ref(),
            ErrorKind::Write(WriteFailure::WriteError(we)) if we.code == 11000
        )
    }

    pub async fn idempotent_insert(
        coll: &Collection<Document>,
        mut doc: Document,
        key: &str,
    ) -> anyhow::Result<bool> {
        doc.insert("idempotency_key", key);
        doc.insert("idempotency_created", chrono::Utc::now());
        match coll.insert_one(doc).await {
            Ok(_) => Ok(true),
            Err(e) if is_duplicate_key(&e) => Ok(false),
            Err(e) => Err(e.into()),
        }
    }

    pub async fn optimistic_update(
        coll: &Collection<Document>,
        id: &str,
        expected_ver: i64,
        update: Document,
    ) -> anyhow::Result<bool> {
        let res = coll.update_one(
            doc! { "_id": id, "_ver": expected_ver },
            doc! { "$set": update, "$inc": { "_ver": 1 } },
        ).await?;
        Ok(res.modified_count == 1)
    }
}

pub mod outbox {
    use mongodb::bson::{doc, Document};
    use serde::Serialize;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;
    use tokio::sync::RwLock;

    #[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
    pub struct OutboxEntry {
        pub seq: u64,
        pub collection: String,
        pub document: Document,
        pub journaled: chrono::DateTime<chrono::Utc>,
        pub confirmed: bool,
    }

    pub struct Outbox {
        pending: Arc<RwLock<Vec<OutboxEntry>>>,
        pub journaled_total: AtomicU64,
        pub confirmed_total: AtomicU64,
        cap: usize,
    }

    impl Default for Outbox {
        fn default() -> Self { Self::new(4096) }
    }

    impl Outbox {
        pub fn new(cap: usize) -> Self {
            Self {
                pending: Arc::new(RwLock::new(Vec::with_capacity(cap.min(1024)))),
                journaled_total: AtomicU64::new(0),
                confirmed_total: AtomicU64::new(0),
                cap,
            }
        }

        pub async fn journal<T: Serialize>(&self, collection: &str, value: &T) -> anyhow::Result<u64> {
            let document = mongodb::bson::to_document(value)?;
            let seq = self.journaled_total.fetch_add(1, Ordering::Relaxed) + 1;
            let entry = OutboxEntry {
                seq,
                collection: collection.to_string(),
                document,
                journaled: chrono::Utc::now(),
                confirmed: false,
            };
            let mut pending = self.pending.write().await;
            if pending.len() >= self.cap {
                anyhow::bail!("outbox full — durable persistence is backpressured, not dropped");
            }
            pending.push(entry);
            Ok(seq)
        }

        pub async fn confirm_one(&self, seq: u64) -> anyhow::Result<bool> {
            let doc_and_coll = {
                let pending = self.pending.read().await;
                pending.iter().find(|e| e.seq == seq && !e.confirmed)
                    .map(|e| (e.collection.clone(), e.document.clone()))
            };
            let Some((collection, document)) = doc_and_coll else { return Ok(true) };
            let db = crate::db::get_db().await?;
            db.collection::<Document>(&collection).insert_one(document).await?;
            let mut pending = self.pending.write().await;
            if let Some(e) = pending.iter_mut().find(|e| e.seq == seq) {
                e.confirmed = true;
            }
            pending.retain(|e| !e.confirmed);
            self.confirmed_total.fetch_add(1, Ordering::Relaxed);
            Ok(true)
        }

        pub async fn reconcile(&self) -> usize {
            let seqs: Vec<u64> = {
                let pending = self.pending.read().await;
                pending.iter().filter(|e| !e.confirmed).map(|e| e.seq).collect()
            };
            let mut done = 0;
            for seq in seqs {
                if self.confirm_one(seq).await.is_ok() { done += 1; }
            }
            done
        }

        pub async fn pending_count(&self) -> usize {
            self.pending.read().await.iter().filter(|e| !e.confirmed).count()
        }
    }

    pub fn spawn_reconciler(outbox: Arc<Outbox>, interval: std::time::Duration) {
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(interval).await;
                let n = outbox.reconcile().await;
                if n > 0 { tracing::info!(confirmed = n, "outbox reconciler swept"); }
            }
        });
    }

    pub fn doc() -> Document { doc! {} }
}

pub mod bus {
    use tokio::sync::broadcast;
    use serde::{Serialize, Deserialize};
    use chrono::{DateTime, Utc};

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct Event {
        pub topic: String,
        pub payload: serde_json::Value,
        pub ts: DateTime<Utc>,
        pub seq: u64,
    }

    #[derive(Clone)]
    pub struct EventBus {
        tx: broadcast::Sender<Event>,
        seq: Arc<RwLock<u64>>,
    }

    impl EventBus {
        pub fn new(capacity: usize) -> Self {
            let (tx, _) = broadcast::channel(capacity);
            Self { tx, seq: Arc::new(RwLock::new(0)) }
        }

        pub fn subscribe(&self) -> broadcast::Receiver<Event> { self.tx.subscribe() }

        pub async fn publish(&self, topic: &str, payload: serde_json::Value) {
            let mut seq = self.seq.write().await;
            *seq += 1;
            let ev = Event { topic: topic.into(), payload, ts: Utc::now(), seq: *seq };
            let _ = self.tx.send(ev.clone());
            if let Ok(db) = crate::db::get_db().await {
                let _ = db.collection::<Event>("prood_event_log").insert_one(ev).await;
            }
        }
    }
}

pub use mongodb::bson::{doc, Document};
