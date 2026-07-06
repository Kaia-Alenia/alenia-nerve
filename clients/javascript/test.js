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
const { NexusClient } = require('./index');

/**
 * Creates a mock hub server on a random port.
 * Returns { server, port }.
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

async function runTests() {
  console.log('Running JavaScript client test suite...');

  const hub = await createMockHub();
  const { server, port } = hub;
  let { connections } = hub;
  console.log(`Mock hub listening on 127.0.0.1:${port}`);

  try {
    // 1. Connection and handshake
    const client = makeClient(port);
    await client.connect('test_client');
    assert.strictEqual(client.clientId, 'test_client');
    assert.strictEqual(client.connecting, false);
    console.log('✓ Connection and handshake passed.');

    // 2. listClients and list_clients alias
    const clients = await client.listClients();
    assert.deepStrictEqual(clients, ['test_client', 'dummy_peer']);
    const clientsAlt = await client.list_clients();
    assert.deepStrictEqual(clientsAlt, ['test_client', 'dummy_peer']);
    console.log('✓ listClients and list_clients commands passed.');

    // 3. listen/events and receive message
    let receivedPayload = null;
    let eventReceivedPayload = null;

    client.listen((msg) => { receivedPayload = msg.payload; });
    client.on('message', (msg) => { eventReceivedPayload = msg.payload; });

    client.send('dummy_peer', { hello: 'world' });
    await new Promise((r) => setTimeout(r, 80));
    assert.deepStrictEqual(receivedPayload, { hello: 'world' });
    assert.deepStrictEqual(eventReceivedPayload, { hello: 'world' });
    console.log('✓ send, listen, and event message reception passed.');

    // 4. broadcast command
    receivedPayload = null;
    client.broadcast({ all: 'nodes' });
    await new Promise((r) => setTimeout(r, 80));
    assert.deepStrictEqual(receivedPayload, { all: 'nodes' });
    console.log('✓ broadcast and message reception passed.');

    // 5. Auto-reconnection
    let reconnected = false;
    client.listen(() => {}, () => { reconnected = true; });

    console.log('Simulating connection loss...');
    for (const conn of connections) conn.destroy();
    connections = [];

    await new Promise((r) => setTimeout(r, 400));
    assert.strictEqual(reconnected, true);
    console.log('✓ Auto-reconnection passed.');

    // 6. Authentication failure
    const authClient = makeClient(port, 'invalid_token');
    await assert.rejects(
      authClient.connect('auth_failure_client'),
      /Authentication failed/
    );
    assert.strictEqual(authClient.closed, true);
    console.log('✓ Authentication failure handling passed.');

    // 7. Graceful disconnect
    client.disconnect();
    authClient.disconnect();
    console.log('✓ Graceful disconnection passed.');

    console.log('\nAll JavaScript client tests passed successfully.');
    server.close();
    process.exit(0);
  } catch (error) {
    console.error('\nJavaScript client tests FAILED:', error);
    server.close();
    process.exit(1);
  }
}

runTests();
