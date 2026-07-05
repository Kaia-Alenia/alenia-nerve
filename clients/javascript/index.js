class NexusClient {
  constructor() {
    this.clientId = null;
  }

  connect(clientId) {
    this.clientId = clientId;
    return true;
  }
}

module.exports = { NexusClient };
