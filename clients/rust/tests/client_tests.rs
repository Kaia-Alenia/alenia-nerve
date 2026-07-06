use alenia_nerve::{ConnectionAddress, NexusClient, SyncNexusClient};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpListener;

fn ok_response() -> String {
    format!(
        "{}\n",
        serde_json::json!({"type": "registered", "status": "success"})
    )
}

#[tokio::test]
async fn test_nexus_client_async() {
    let server = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = server.local_addr().unwrap().port();

    let server_handle = tokio::spawn(async move {
        if let Ok((mut stream, _)) = server.accept().await {
            let (r, mut w) = stream.split();
            let mut reader = BufReader::new(r);
            let mut line = String::new();
            if let Ok(n) = reader.read_line(&mut line).await {
                if n > 0 {
                    let reg: serde_json::Value = serde_json::from_str(&line).unwrap();
                    assert_eq!(reg["type"], "register");
                    assert_eq!(reg["id"], "test_async_client");
                    w.write_all(ok_response().as_bytes()).await.unwrap();
                }
            }
        }
    });

    let mut client = NexusClient::new(Duration::from_millis(100), "non_existent.config", None);
    client.address = ConnectionAddress::Tcp("127.0.0.1".to_string(), port);
    client.is_windows = true;

    assert!(client.connect("test_async_client").await.is_ok());

    client.disconnect();
    let _ = server_handle.await;
}

#[tokio::test]
async fn test_nexus_client_sync() {
    let server = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = server.local_addr().unwrap().port();

    let server_handle = tokio::spawn(async move {
        if let Ok((mut stream, _)) = server.accept().await {
            let (r, mut w) = stream.split();
            let mut reader = BufReader::new(r);
            let mut line = String::new();
            if let Ok(n) = reader.read_line(&mut line).await {
                if n > 0 {
                    let reg: serde_json::Value = serde_json::from_str(&line).unwrap();
                    assert_eq!(reg["type"], "register");
                    assert_eq!(reg["id"], "test_sync_client");
                    w.write_all(ok_response().as_bytes()).await.unwrap();
                }
            }
        }
    });

    let mut client = NexusClient::new(Duration::from_millis(100), "non_existent.config", None);
    client.address = ConnectionAddress::Tcp("127.0.0.1".to_string(), port);
    client.is_windows = true;

    assert!(client.connect("test_sync_client").await.is_ok());

    client.disconnect();
    let _ = server_handle.await;
}

#[test]
fn test_sync_wrapper() {
    let sync_client = SyncNexusClient::new(Duration::from_millis(100), "non_existent.config", None);
    sync_client.disconnect();
}
