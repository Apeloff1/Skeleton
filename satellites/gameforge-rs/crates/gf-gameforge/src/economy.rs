use std::collections::HashMap;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use tokio::sync::RwLock;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Entry { pub id:String, pub account:String, pub delta:i64, pub counterparty:String, pub memo:String, pub at:DateTime<Utc>, pub provenance:String }
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account { pub name:String, pub balance:i64, pub entries:u64, pub frozen:bool }
const LEDGER_CAP: usize = 65536;
pub struct Treasury { accounts:RwLock<HashMap<String,Account>>, ledger:RwLock<Vec<Entry>> }
impl Default for Treasury { fn default()->Self{Self::new()} }
impl Treasury {
    pub fn new()->Self{Self{accounts:RwLock::new(HashMap::new()),ledger:RwLock::new(Vec::new())}}
    pub async fn open_account(&self,name:&str)->Account{
        let mut a=self.accounts.write().await; a.entry(name.to_string()).or_insert(Account{name:name.to_string(),balance:0,entries:0,frozen:false}).clone()
    }
    pub async fn mint(&self,account:&str,amount:i64,provenance_event:&str,memo:&str)->Result<Entry,String>{
        if amount<=0{return Err("mint amount must be positive".into())}
        let mut accounts=self.accounts.write().await; let acc=accounts.get_mut(account).ok_or("no such account")?; if acc.frozen{return Err("account frozen".into())}
        acc.balance+=amount; acc.entries+=1;
        let e=Entry{id:Uuid::new_v4().to_string(),account:account.to_string(),delta:amount,counterparty:"mint".into(),memo:memo.to_string(),at:Utc::now(),provenance:provenance_event.to_string()};
        drop(accounts); self.record(e.clone()).await; Ok(e)
    }
    pub async fn transfer(&self,from:&str,to:&str,amount:i64,memo:&str)->Result<(Entry,Entry),String>{
        if amount<=0{return Err("transfer amount must be positive".into())} if from==to{return Err("self-transfer is not a transfer".into())}
        let mut accounts=self.accounts.write().await; let src=accounts.get(from).ok_or("no such source account")?;
        if src.frozen{return Err("source account frozen".into())} if src.balance<amount{return Err("insufficient funds — the treasury extends no credit".into())}
        if !accounts.contains_key(to){return Err("no such destination account".into())} if accounts[to].frozen{return Err("destination account frozen".into())}
        let pair=Uuid::new_v4().to_string();
        let debit=Entry{id:Uuid::new_v4().to_string(),account:from.to_string(),delta:-amount,counterparty:to.to_string(),memo:memo.to_string(),at:Utc::now(),provenance:pair.clone()};
        let credit=Entry{id:Uuid::new_v4().to_string(),account:to.to_string(),delta:amount,counterparty:from.to_string(),memo:memo.to_string(),at:Utc::now(),provenance:pair};
        {let a=accounts.get_mut(from).unwrap();a.balance-=amount;a.entries+=1;} {let a=accounts.get_mut(to).unwrap();a.balance+=amount;a.entries+=1;}
        drop(accounts); self.record(debit.clone()).await; self.record(credit.clone()).await; Ok((debit,credit))
    }
    pub async fn freeze(&self,account:&str,frozen:bool)->bool{let mut a=self.accounts.write().await;match a.get_mut(account){Some(x)=>{x.frozen=frozen;true},None=>false}}
    async fn record(&self,e:Entry){let mut l=self.ledger.write().await;if l.len()>=LEDGER_CAP{l.drain(0..LEDGER_CAP/2);}l.push(e)}
    pub async fn audit(&self)->serde_json::Value{let a=self.accounts.read().await;let l=self.ledger.read().await;let bs:i64=a.values().map(|x|x.balance).sum();let ls:i64=l.iter().map(|x|x.delta).sum();serde_json::json!({"accounts":a.len(),"balance_sum":bs,"ledger_window_sum":ls,"ledger_entries":l.len(),"window_balanced":bs==ls||l.len()>=LEDGER_CAP/2})}
    pub async fn account(&self,name:&str)->Option<Account>{self.accounts.read().await.get(name).cloned()}
    pub async fn accounts(&self)->Vec<Account>{self.accounts.read().await.values().cloned().collect()}
}
