/*! Nerve — Decentralized Nervous System for Local Sockets.
 * Rust client library implementation.
 *
 * Built by Alenia Studios.
 * License: GNU General Public License v3 (GPL v3)
 */

use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader as StdBufReader};
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpStream, UnixStream};
use tokio::sync::{mpsc, oneshot, Mutex};
use tokio::time::sleep;

type IoHalves = (
    Box<dyn tokio::io::AsyncRead + Send + Unpin>,
    Box<dyn tokio::io::AsyncWrite + Send + Unpin>,
);

#[derive(Clone)]
pub enum ConnectionAddress {
    Tcp(String, u16),
    Unix(String),
}

fn load_external_config(config_path: &str) -> HashMap<String, String> {
    let mut config = HashMap::new();
    let path = Path::new(config_path);
    if !path.exists() {
        return config;
    }

    if let Ok(file) = File::open(path) {
        if let Ok(json_val) = serde_json::from_reader::<_, serde_json::Value>(&file) {
            if let Some(obj) = json_val.as_object() {
                for (k, v) in obj {
                    if let Some(s) = v.as_str() {
                        config.insert(k.clone(), s.to_string());
                    } else if let Some(i) = v.as_i64() {
                        config.insert(k.clone(), i.to_string());
                    } else if let Some(b) = v.as_bool() {
                        config.insert(k.clone(), b.to_string());
                    }
                }
                return config;
            }
        }
    }

    if let Ok(file) = File::open(path) {
        let reader = StdBufReader::new(file);
        for line in reader.lines().map_while(Result::ok) {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(pos) = line.find('=') {
                let key = line[..pos].trim().to_string();
                let val = line[pos + 1..].trim().to_string();
                config.insert(key, val);
            }
        }
    }
    config
}

pub struct NexusClient {
    client_id: Option<String>,
    retry_interval: Duration,
    auth_token: Option<String>,
    pub address: ConnectionAddress,
    tx: Arc<Mutex<Option<mpsc::UnboundedSender<String>>>>,
    list_resolvers: Arc<Mutex<Vec<oneshot::Sender<Vec<String>>>>>,
    listeners: Arc<Mutex<Vec<mpsc::UnboundedSender<serde_json::Value>>>>,
    on_reconnect_listeners: Arc<Mutex<Vec<mpsc::UnboundedSender<()>>>>,
    closed: Arc<Mutex<bool>>,
    pub is_windows: bool,
}

impl NexusClient {
    pub fn new(retry_interval: Duration, config_path: &str, auth_token: Option<String>) -> Self {
        let config = load_external_config(config_path);
        let is_windows = cfg!(target_os = "windows");

        let token = auth_token.or_else(|| config.get("auth_token").cloned());

        let address = if is_windows {
            let host = config
                .get("host")
                .cloned()
                .unwrap_or_else(|| "127.0.0.1".to_string());
            let port = config
                .get("port")
                .and_then(|p| p.parse::<u16>().ok())
                .unwrap_or(50505);
            ConnectionAddress::Tcp(host, port)
        } else {
            let path = config
                .get("socket_path")
                .or_else(|| config.get("socketPath"))
                .cloned()
                .unwrap_or_else(|| "/tmp/nerve.sock".to_string());
            ConnectionAddress::Unix(path)
        };

        Self {
            client_id: None,
            retry_interval,
            auth_token: token,
            address,
            tx: Arc::new(Mutex::new(None)),
            list_resolvers: Arc::new(Mutex::new(Vec::new())),
            listeners: Arc::new(Mutex::new(Vec::new())),
            on_reconnect_listeners: Arc::new(Mutex::new(Vec::new())),
            closed: Arc::new(Mutex::new(false)),
            is_windows,
        }
    }

    pub async fn connect(
        &mut self,
        client_id: &str,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        self.client_id = Some(client_id.to_string());
        let (connect_ok_tx, connect_ok_rx) = oneshot::channel();

        let client_id_str = client_id.to_string();
        let retry_interval = self.retry_interval;
        let address = self.address.clone();
        let auth_token = self.auth_token.clone();
        let list_resolvers = self.list_resolvers.clone();
        let listeners = self.listeners.clone();
        let on_reconnect_listeners = self.on_reconnect_listeners.clone();
        let tx_shared = self.tx.clone();
        let closed = self.closed.clone();
        let is_windows = self.is_windows;

        tokio::spawn(async move {
            let mut first_connect = Some(connect_ok_tx);

            while !*closed.lock().await {
                let conn_result: Result<IoHalves, std::io::Error> = if is_windows {
                    match &address {
                        ConnectionAddress::Tcp(host, port) => {
                            match TcpStream::connect(format!("{}:{}", host, port)).await {
                                Ok(stream) => {
                                    let (r, w) = tokio::io::split(stream);
                                    Ok((Box::new(r), Box::new(w)))
                                }
                                Err(e) => Err(e),
                            }
                        }
                        _ => Err(std::io::Error::other("Invalid address for Windows")),
                    }
                } else {
                    match &address {
                        ConnectionAddress::Unix(path) => match UnixStream::connect(path).await {
                            Ok(stream) => {
                                let (r, w) = tokio::io::split(stream);
                                Ok((Box::new(r), Box::new(w)))
                            }
                            Err(e) => Err(e),
                        },
                        _ => Err(std::io::Error::other("Invalid address for Unix")),
                    }
                };

                let (read_half, mut write_half) = match conn_result {
                    Ok(halves) => halves,
                    Err(e) => {
                        println!(
                            "[NERVE] Hub unavailable ({}). Retrying in {}s...",
                            e,
                            retry_interval.as_secs_f32()
                        );
                        sleep(retry_interval).await;
                        continue;
                    }
                };

                let reg_msg = if let Some(token) = &auth_token {
                    serde_json::json!({
                        "type": "register",
                        "id": client_id_str,
                        "token": token
                    })
                } else {
                    serde_json::json!({
                        "type": "register",
                        "id": client_id_str
                    })
                };

                if write_half
                    .write_all(format!("{}\n", reg_msg).as_bytes())
                    .await
                    .is_err()
                {
                    sleep(retry_interval).await;
                    continue;
                }

                let mut reader = BufReader::new(read_half);
                let mut line = String::new();

                let handshake_timeout = sleep(Duration::from_secs(5));
                tokio::pin!(handshake_timeout);

                let mut handshake_ok = false;
                let mut auth_failed = false;

                tokio::select! {
                    res = reader.read_line(&mut line) => {
                        if let Ok(n) = res {
                            if n > 0 {
                                if let Ok(val) = serde_json::from_str::<serde_json::Value>(&line) {
                                    if val["type"] == "registered" {
                                        if val["status"] == "success" {
                                            handshake_ok = true;
                                        } else if val["status"] == "failed" && val["reason"] == "auth" {
                                            auth_failed = true;
                                        }
                                    }
                                }
                            }
                        }
                    }
                    _ = &mut handshake_timeout => {}
                }

                if auth_failed {
                    println!(
                        "[NERVE] Connected to hub as '{}' failed (auth).",
                        client_id_str
                    );
                    *closed.lock().await = true;
                    if let Some(chan) = first_connect.take() {
                        let _ = chan.send(Err("Authentication failed".into()));
                    }
                    break;
                }

                if !handshake_ok {
                    sleep(retry_interval).await;
                    continue;
                }

                println!("[NERVE] Connected to hub as '{}'.", client_id_str);

                let (write_tx, mut write_rx) = mpsc::unbounded_channel::<String>();
                *tx_shared.lock().await = Some(write_tx);

                let is_reconnect = first_connect.is_none();
                if let Some(chan) = first_connect.take() {
                    let _ = chan.send(Ok(()));
                }

                if is_reconnect {
                    let r_listeners = on_reconnect_listeners.lock().await;
                    for listener in r_listeners.iter() {
                        let _ = listener.send(());
                    }
                }

                let read_resolvers = list_resolvers.clone();
                let read_listeners = listeners.clone();
                let read_closed = closed.clone();

                let read_handle = tokio::spawn(async move {
                    let mut reader_line = String::new();
                    while !*read_closed.lock().await {
                        reader_line.clear();
                        match reader.read_line(&mut reader_line).await {
                            Ok(n) if n > 0 => {
                                if let Ok(val) =
                                    serde_json::from_str::<serde_json::Value>(&reader_line)
                                {
                                    let msg_type = val["type"].as_str().unwrap_or("");
                                    if msg_type == "ping" || msg_type == "pong" {
                                        continue;
                                    }
                                    if msg_type == "list" {
                                        let clients: Vec<String> = val["clients"]
                                            .as_array()
                                            .unwrap_or(&Vec::new())
                                            .iter()
                                            .filter_map(|c| c.as_str().map(|s| s.to_string()))
                                            .collect();

                                        let mut resolvers = read_resolvers.lock().await;
                                        if !resolvers.is_empty() {
                                            let res = resolvers.remove(0);
                                            let _ = res.send(clients);
                                        }
                                    } else {
                                        let l_list = read_listeners.lock().await;
                                        for listener in l_list.iter() {
                                            let _ = listener.send(val.clone());
                                        }
                                    }
                                }
                            }
                            _ => break,
                        }
                    }
                });

                let write_closed = closed.clone();
                let write_handle = tokio::spawn(async move {
                    while !*write_closed.lock().await {
                        if let Some(msg) = write_rx.recv().await {
                            if write_half.write_all(msg.as_bytes()).await.is_err() {
                                break;
                            }
                        } else {
                            break;
                        }
                    }
                });

                tokio::select! {
                    _ = read_handle => {}
                    _ = write_handle => {}
                }

                *tx_shared.lock().await = None;
                if *closed.lock().await {
                    break;
                }
                println!("[NERVE] Hub connection lost. Reconnecting...");
            }
        });

        match connect_ok_rx.await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(e)) => Err(e),
            Err(_) => Err("Connection thread panicked".into()),
        }
    }

    pub fn disconnect(&self) {
        if let Ok(mut closed_guard) = self.closed.try_lock() {
            *closed_guard = true;
        }
        if let Ok(mut tx_guard) = self.tx.try_lock() {
            *tx_guard = None;
        }
        if let Some(id) = &self.client_id {
            println!("[NERVE] '{}' disconnected.", id);
        }
    }

    fn send_raw(
        &self,
        msg: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let tx_lock = self.tx.try_lock()?;
        if let Some(tx) = &*tx_lock {
            tx.send(format!("{}\n", msg))?;
            Ok(())
        } else {
            Err("Not connected to hub.".into())
        }
    }

    pub fn send(
        &self,
        to: &str,
        payload: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        self.send_raw(serde_json::json!({
            "type": "send",
            "to": to,
            "payload": payload
        }))
    }

    pub fn broadcast(
        &self,
        payload: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        self.send_raw(serde_json::json!({
            "type": "broadcast",
            "payload": payload
        }))
    }

    pub async fn list_clients(
        &self,
    ) -> Result<Vec<String>, Box<dyn std::error::Error + Send + Sync>> {
        let (res_tx, res_rx) = oneshot::channel();
        {
            let mut resolvers = self.list_resolvers.lock().await;
            resolvers.push(res_tx);
        }

        self.send_raw(serde_json::json!({ "type": "list" }))?;

        tokio::select! {
            res = res_rx => {
                match res {
                    Ok(clients) => Ok(clients),
                    Err(_) => Err("Request cancelled".into())
                }
            }
            _ = sleep(Duration::from_secs(2)) => {
                Err("Timeout listing clients".into())
            }
        }
    }

    pub async fn listen<F>(
        &self,
        callback: F,
        on_reconnect: Option<Box<dyn Fn() + Send + Sync + 'static>>,
    ) where
        F: Fn(serde_json::Value) + Send + Sync + 'static,
    {
        let (msg_tx, mut msg_rx) = mpsc::unbounded_channel::<serde_json::Value>();
        {
            let mut list = self.listeners.lock().await;
            list.push(msg_tx);
        }

        tokio::spawn(async move {
            while let Some(msg) = msg_rx.recv().await {
                callback(msg);
            }
        });

        if let Some(cb) = on_reconnect {
            let (rec_tx, mut rec_rx) = mpsc::unbounded_channel::<()>();
            {
                let mut list = self.on_reconnect_listeners.lock().await;
                list.push(rec_tx);
            }
            tokio::spawn(async move {
                while rec_rx.recv().await.is_some() {
                    cb();
                }
            });
        }
    }
}

pub struct SyncNexusClient {
    async_client: Arc<Mutex<NexusClient>>,
    rt: tokio::runtime::Runtime,
}

impl SyncNexusClient {
    pub fn new(retry_interval: Duration, config_path: &str, auth_token: Option<String>) -> Self {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();
        let async_client =
            rt.block_on(async { NexusClient::new(retry_interval, config_path, auth_token) });
        Self {
            async_client: Arc::new(Mutex::new(async_client)),
            rt,
        }
    }

    pub fn connect(&self, client_id: &str) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = self.async_client.clone();
        let client_id = client_id.to_string();
        self.rt.block_on(async move {
            let mut guard = client.lock().await;
            guard.connect(&client_id).await
        })
    }

    pub fn disconnect(&self) {
        let client = self.async_client.clone();
        self.rt.block_on(async move {
            let guard = client.lock().await;
            guard.disconnect();
        });
    }

    pub fn send(
        &self,
        to: &str,
        payload: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = self.async_client.clone();
        let to = to.to_string();
        self.rt.block_on(async move {
            let guard = client.lock().await;
            guard.send(&to, payload)
        })
    }

    pub fn broadcast(
        &self,
        payload: serde_json::Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let client = self.async_client.clone();
        self.rt.block_on(async move {
            let guard = client.lock().await;
            guard.broadcast(payload)
        })
    }

    pub fn list_clients(&self) -> Result<Vec<String>, Box<dyn std::error::Error + Send + Sync>> {
        let client = self.async_client.clone();
        self.rt.block_on(async move {
            let guard = client.lock().await;
            guard.list_clients().await
        })
    }

    pub fn listen<F>(
        &self,
        callback: F,
        on_reconnect: Option<Box<dyn Fn() + Send + Sync + 'static>>,
    ) where
        F: Fn(serde_json::Value) + Send + Sync + 'static,
    {
        let client = self.async_client.clone();
        self.rt.block_on(async move {
            let guard = client.lock().await;
            guard.listen(callback, on_reconnect).await;
        });
    }
}
