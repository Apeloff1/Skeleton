#[tokio::main]
async fn main() -> anyhow::Result<()> {
    gf_server::serve().await
}
