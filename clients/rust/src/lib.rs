pub struct NexusClient {
    pub client_id: Option<String>,
}

impl NexusClient {
    pub fn new() -> Self {
        Self { client_id: None }
    }

    pub fn connect(&mut self, client_id: &str) -> bool {
        self.client_id = Some(client_id.to_string());
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_connect() {
        let mut client = NexusClient::new();
        assert!(client.connect("test_client"));
    }
}
