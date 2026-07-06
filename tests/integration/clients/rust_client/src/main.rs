use alenia_nerve::SyncNexusClient;
use std::sync::Arc;
use std::time::Duration;

fn main() {
    // Resolve the nerve.config at the project root (4 levels up from this binary's workspace).
    // Falls back to /tmp/nerve.sock via defaults if the file is absent.
    let config_path = std::env::var("NERVE_CONFIG")
        .unwrap_or_else(|_| "nerve.config".to_string());

    let client = Arc::new(SyncNexusClient::new(
        Duration::from_secs(1),
        &config_path,
        None,
    ));
    client.connect("rs_client").unwrap();

    let client_clone = Arc::clone(&client);
    client.listen(
        move |msg| {
            // msg is the full message dict: {"type": ..., "payload": ..., "from": ...}
            let payload = &msg["payload"];
            if payload["event"] == "ping" {
                if let Some(timestamp) = payload["timestamp"].as_f64() {
                    let _ = client_clone.broadcast(serde_json::json!({
                        "event": "pong",
                        "from": "rs_client",
                        "timestamp": timestamp,
                    }));
                }
            }
        },
        None,
    );

    // Keep the process alive until SIGTERM sent by the test harness.
    loop {
        std::thread::sleep(Duration::from_secs(1));
    }
}
