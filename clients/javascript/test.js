/**
 * Nerve — Decentralized Nervous System for Local Sockets.
 * JavaScript/Node.js client tests.
 *
 * Built by Alenia Studios.
 * License: GNU General Public License v3 (GPL v3)
 */

'use strict';

const assert = require('assert');
const net = require('net');
const fs = require('fs');
const { NexusClient } = require('./index');

/**
 * Creates a mock hub server on a random port.
 * Returns { server, port, connections }.
 */
function createMockHub() {
  const connections = [];
  const server = net.createServer((socket) => {
    connections.push(socket);
    let buffer = '';

    socket.on('data', (chunk) => {
      buffer += chunk.toString('utf8');
      let boundary = buffer.indexOf('\n');
      while (boundary !== -1) {
        const line = buffer.substring(0, boundary).trim();
        buffer = buffer.substring(boundary + 1);

        if (line) {
          try {
            const msg = JSON.parse(line);
            if (msg.type === 'register') {
              if (msg.token && msg.token === 'invalid_token') {
                socket.write(JSON.stringify({ type: 'registered', status: 'failed', reason: 'auth' }) + '\n');
              } else {
                socket.write(JSON.stringify({ type: 'registered', status: 'success' }) + '\n');
              }
            } else if (msg.type === 'list') {
              socket.write(JSON.stringify({ type: 'list', clients: ['test_client', 'dummy_peer'] }) + '\n');
            } else if (msg.type === 'send') {
              socket.write(JSON.stringify({ type: 'message', from: msg.to, payload: msg.payload }) + '\n');
            } else if (msg.type === 'broadcast') {
              socket.write(JSON.stringify({ type: 'message', from: 'hub', payload: msg.payload }) + '\n');
            }
          } catch (_) {}
        }
        boundary = buffer.indexOf('\n');
      }
    });
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, port, connections });
    });
  });
}

function makeClient(port, token) {
  const opts = { retryInterval: 0.1 };
  if (token) opts.authToken = token;
  const client = new NexusClient(opts);
  client.address = { host: '127.0.0.1', port };
  client.isWindows = true;
  return client;
}

describe('NexusClient', function () {
  let hub, server, port, connections;
  let client;

  before(async function () {
    hub = await createMockHub();
    server = hub.server;
    port = hub.port;
    connections = hub.connections;
  });

  after(function () {
    if (server) {
      server.close();
    }
  });

  afterEach(function () {
    if (client && !client.closed) {
      client.disconnect();
    }
  });

  it('1. should connect and perform handshake', async function () {
    client = makeClient(port);
    await client.connect('test_client');
    assert.strictEqual(client.clientId, 'test_client');
    assert.strictEqual(client.connecting, false);
  });

  it('2. should list clients', async function () {
    client = makeClient(port);
    await client.connect('test_client');

    const clients = await client.listClients();
    assert.deepStrictEqual(clients, ['test_client', 'dummy_peer']);
    
    const clientsAlt = await client.list_clients();
    assert.deepStrictEqual(clientsAlt, ['test_client', 'dummy_peer']);
  });

  it('3. should listen to events and receive message', async function () {
    client = makeClient(port);
    await client.connect('test_client');

    let receivedPayload = null;
    let eventReceivedPayload = null;

    client.listen((msg) => { receivedPayload = msg.payload; });
    client.on('message', (msg) => { eventReceivedPayload = msg.payload; });

    client.send('dummy_peer', { hello: 'world' });
    await new Promise((r) => setTimeout(r, 80));
    
    assert.deepStrictEqual(receivedPayload, { hello: 'world' });
    assert.deepStrictEqual(eventReceivedPayload, { hello: 'world' });
  });

  it('4. should send and receive broadcast command', async function () {
    client = makeClient(port);
    await client.connect('test_client');

    let receivedPayload = null;
    client.listen((msg) => { receivedPayload = msg.payload; });
    
    client.broadcast({ all: 'nodes' });
    await new Promise((r) => setTimeout(r, 80));
    
    assert.deepStrictEqual(receivedPayload, { all: 'nodes' });
  });

  it('5. should auto-reconnect on connection loss', async function () {
    client = makeClient(port);
    await client.connect('test_client');

    let reconnected = false;
    client.listen(() => {}, () => { reconnected = true; });

    // Force disconnect
    for (const conn of connections) {
      conn.destroy();
    }
    // Clear connections to ensure we aren't tracking old ones
    connections.length = 0;

    await new Promise((r) => setTimeout(r, 400));
    assert.strictEqual(reconnected, true);
  });

  it('6. should handle authentication failure', async function () {
    const authClient = makeClient(port, 'invalid_token');
    await assert.rejects(
      authClient.connect('auth_failure_client'),
      /Authentication failed/
    );
    assert.strictEqual(authClient.closed, true);
  });
  
  it('7. should handle invalid JSON', async function () {
    client = makeClient(port);
    await client.connect('test_client');
    
    let crashed = false;
    const crashListener = (err) => {
      crashed = true;
    };
    process.on('uncaughtException', crashListener);
    client.socket.emit('data', Buffer.from('{invalid: json}\\n'));
    await new Promise((r) => setTimeout(r, 80));
    assert.strictEqual(crashed, false);
    process.removeListener('uncaughtException', crashListener);
  });

  it('8. should swallow SSL configuration errors on retry', async function () {
    const originalReadFileSync = fs.readFileSync;
    let mockCaRead = false;
    let sslErrorSwallowed = true;

    try {
      fs.readFileSync = (filepath, options) => {
        if (filepath === 'dummy_missing_ca.pem') {
          mockCaRead = true;
          throw new Error('Simulated CA read error');
        }
        return originalReadFileSync(filepath, options);
      };

      const sslClient = new NexusClient({
        useSsl: true,
        sslCa: 'dummy_missing_ca.pem',
        retryInterval: 0.1
      });
      sslClient.address = { host: '127.0.0.1', port };
      sslClient.isWindows = true;

      try {
        sslClient._connectLoop(() => {}, () => {});
      } catch (err) {
        if (err.message === 'Simulated CA read error') {
          sslErrorSwallowed = false;
        }
      }

      assert.strictEqual(mockCaRead, true);
      assert.strictEqual(sslErrorSwallowed, true);
      sslClient.disconnect();
    } finally {
      fs.readFileSync = originalReadFileSync;
    }
  });

  it('9. should disconnect gracefully', async function () {
    client = makeClient(port);
    await client.connect('test_client');
    client.disconnect();
    assert.strictEqual(client.closed, true);
  });
});
