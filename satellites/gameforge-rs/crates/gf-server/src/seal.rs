use axum::http::{HeaderMap, StatusCode};
use axum::response::IntoResponse;
use sha2::{Digest, Sha256};
use std::time::{SystemTime, UNIX_EPOCH};

pub const SEAL_HEADER: &str = "x-gf-seal";

fn secret() -> Option<Vec<u8>> {
    std::env::var("GF_SEAL_SECRET").ok().map(|s| s.into_bytes()).filter(|s| !s.is_empty())
}

fn ct_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() { return false; }
    a.iter().zip(b.iter()).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

fn seal_payload(attester: &str, expiry: u64) -> String { format!("{attester}|{expiry}") }

fn expected_sig(payload: &str, secret: &[u8]) -> String {
    let mut ipad = vec![0x36u8; 64];
    let mut opad = vec![0x5cu8; 64];
    let mut key = secret.to_vec();
    if key.len() > 64 { key = Sha256::digest(&key).to_vec(); }
    key.resize(64, 0);
    for i in 0..64 { ipad[i] ^= key[i]; opad[i] ^= key[i]; }
    let mut inner = Sha256::new(); inner.update(&ipad); inner.update(payload.as_bytes()); let inner = inner.finalize();
    let mut outer = Sha256::new(); outer.update(&opad); outer.update(inner); hex::encode(outer.finalize())
}

pub fn mint_seal(attester: &str, ttl_secs: u64) -> Option<String> {
    let secret = secret()?;
    let expiry = SystemTime::now().duration_since(UNIX_EPOCH).ok()?.as_secs() + ttl_secs;
    let payload = seal_payload(attester, expiry);
    Some(format!("{attester}.{expiry}.{}", expected_sig(&payload, &secret)))
}

pub fn verify_seal(headers: &HeaderMap) -> Result<String, StatusCode> {
    let secret = secret().ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    let raw = headers.get(SEAL_HEADER).and_then(|v| v.to_str().ok()).ok_or(StatusCode::UNAUTHORIZED)?;
    let mut parts = raw.rsplitn(3, '.');
    let (sig, expiry_s, attester) = match (parts.next(), parts.next(), parts.next()) { (Some(s), Some(e), Some(a)) => (s, e, a), _ => return Err(StatusCode::UNAUTHORIZED) };
    let expiry: u64 = expiry_s.parse().map_err(|_| StatusCode::UNAUTHORIZED)?;
    let now = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?.as_secs();
    if expiry <= now { return Err(StatusCode::UNAUTHORIZED); }
    let expected = expected_sig(&seal_payload(attester, expiry), &secret);
    if !ct_eq(&expected, sig) { return Err(StatusCode::UNAUTHORIZED); }
    Ok(attester.to_string())
}

pub fn require_seal(headers: &HeaderMap) -> Result<String, axum::response::Response> {
    verify_seal(headers).map_err(|code| (code, axum::Json(serde_json::json!({"error":"invalid or missing seal"}))).into_response())
}
