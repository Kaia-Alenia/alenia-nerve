/**
 * Nerve — Decentralized Nervous System for Local Sockets.
 * Javascript client library implementation.
 *
 * Built by Alenia Studios.
 * License: GNU General Public License v3 (GPL v3)
 */
const net = require('net');
const tls = require('tls');
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const EventEmitter = require('events');

function loadExternalConfig(configPath = 'nerve.config') {
  try {
    if (!fs.existsSync(configPath)) {
      return {};
    }
    const raw = fs.readFileSync(configPath, 'utf8');
    try {
      return JSON.parse(raw);
    } catch (e) {}

    const config = {};
    const lines = raw.split(/\r?\n/);
    for (let line of lines) {
      line = line.trim();
      if (!line || line.startsWith('#')) {
        continue;
      }
      if (line.includes('=')) {
        const idx = line.indexOf('=');
        const key = line.substring(0, idx).trim();
        const val = line.substring(idx + 1).trim();
        config[key] = val;
      }
    }
    return config;
  } catch (e) {
    return {};
  }
}

class NexusClient extends EventEmitter {
  constructor(options = {}) {
    super();
    this.retryInterval = options.retryInterval || 2.0;
    this.configPath = options.configPath || 'nerve.config';
    this.authToken = options.authToken || null;

    const config = loadExternalConfig(this.configPath);
    if (!this.authToken) {
      this.authToken = config.authToken || config.auth_token || null;
    }

    this.useSsl = options.useSsl !== undefined ? options.useSsl : (config.use_ssl === 'true' || config.use_ssl === true);
    this.sslCert = options.sslCert || config.ssl_cert || null;
    this.sslKey = options.sslKey || config.ssl_key || null;
    this.sslCa = options.sslCa || config.ssl_ca || null;
    this.sslInsecure = options.sslInsecure !== undefined ? options.sslInsecure : (config.ssl_insecure === 'true' || config.ssl_insecure === true);

    this.clientId = null;
    this.isWindows = os.platform() === 'win32';

    if (this.isWindows) {
      const host = config.host || '127.0.0.1';
      const port = parseInt(config.port || 50505, 10);
      this.address = { host, port };
    } else {
      this.address = config.socket_path || config.socketPath || '/tmp/nerve.sock';
    }

    this.socket = null;
    this.closed = false;
    this.connecting = false;
    this.buffer = '';
    this.listPromises = [];

    this.setMaxListeners(100);
  }

  connect(clientId) {
    if (!clientId || typeof clientId !== 'string') {
      return Promise.reject(new Error('clientId must be a non-empty string.'));
    }
    this.clientId = clientId;
    this.closed = false;

    return new Promise((resolve, reject) => {
      this._connectLoop(resolve, reject);
    });
  }

  _connectLoop(resolve, reject) {
    if (this.closed) return;
    this.connecting = true;

    const socketOpts = this.isWindows 
      ? { host: this.address.host, port: this.address.port }
      : { path: this.address };

    let socket;
    if (this.useSsl) {
      if (this.sslCa) {
        try { socketOpts.ca = [fs.readFileSync(this.sslCa)]; } catch(e){}
      }
      if (this.sslCert) {
        try { socketOpts.cert = fs.readFileSync(this.sslCert); } catch(e){}
      }
      if (this.sslKey) {
        try { socketOpts.key = fs.readFileSync(this.sslKey); } catch(e){}
      }
      if (this.sslInsecure) socketOpts.rejectUnauthorized = false;
      if (this.isWindows) {
         socketOpts.servername = this.address.host;
      }
      socket = tls.connect(socketOpts);
    } else {
      socket = net.createConnection(socketOpts);
    }
    this.socket = socket;

    socket.setTimeout(5000);
    let connected = false;

    socket.on('connect', () => {
      connected = true;
      const regMsg = { type: 'register', id: this.clientId };
      if (this.authToken) {
        regMsg.token = this.authToken;
      }
      socket.write(JSON.stringify(regMsg) + '\n');
    });

    socket.on('data', (chunk) => {
      this.buffer += chunk.toString('utf8');
      let boundary = this.buffer.indexOf('\n');
      while (boundary !== -1) {
        const line = this.buffer.substring(0, boundary).trim();
        this.buffer = this.buffer.substring(boundary + 1);

        if (line) {
          try {
            const msg = JSON.parse(line);
            
            if (msg.type === 'registered') {
              socket.setTimeout(0);
              if (msg.status === 'success') {
                this.connecting = false;
                this.emit('connect');
                
                if (resolve) {
                  resolve();
                  resolve = null;
                  reject = null;
                } else {
                  this.emit('reconnect');
                }
              } else if (msg.status === 'failed' && msg.reason === 'auth') {
                this.closed = true;
                this.connecting = false;
                socket.destroy();
                const err = new Error('Authentication failed.');
                if (reject) {
                  reject(err);
                  resolve = null;
                  reject = null;
                }
              }
            } else {
              this._handleMessage(msg);
            }
          } catch (err) {}
        }
        boundary = this.buffer.indexOf('\n');
      }
    });

    const handleErrorOrClose = (err) => {
      socket.destroy();
      if (this.socket === socket) {
        this.socket = null;
      }
      this.connecting = false;

      if (this.closed) {
        return;
      }

      this.emit('disconnect');

      setTimeout(() => {
        this._connectLoop(resolve, reject);
      }, this.retryInterval * 1000);
    };

    socket.on('error', (err) => {
      if (!connected) {
        handleErrorOrClose(err);
      } else {
        this.emit('error', err);
      }
    });

    socket.on('timeout', () => {
      if (!connected || this.connecting) {
        handleErrorOrClose(new Error('Handshake timeout'));
      }
    });

    socket.on('close', () => {
      if (connected) {
        handleErrorOrClose(null);
      }
    });
  }

  _handleMessage(msg) {
    if (!msg || typeof msg !== 'object') return;

    const type = msg.type;
    if (type === 'ping' || type === 'pong') {
      return;
    }

    if (type === 'list') {
      const clients = msg.clients || [];
      const promises = this.listPromises;
      this.listPromises = [];
      for (const resolvePromise of promises) {
        resolvePromise(clients);
      }
      return;
    }

    this.emit('message', msg);
  }

  disconnect() {
    this.closed = true;
    if (this.socket) {
      this.socket.destroy();
      this.socket = null;
    }
    this.emit('disconnect');
  }

  _sendWithRetry(message, actionName) {
    if (this.closed || !this.socket) {
      throw new Error('Not connected to hub.');
    }
    try {
      this.socket.write(JSON.stringify(message) + '\n');
    } catch (err) {
      throw err;
    }
  }

  send(to, payload) {
    if (!to || typeof to !== 'string') {
      throw new Error("'to' must be a non-empty string.");
    }
    this._sendWithRetry({ type: 'send', to, payload }, 'Send');
  }

  broadcast(payload) {
    this._sendWithRetry({ type: 'broadcast', payload }, 'Broadcast');
  }

  listClients() {
    return new Promise((resolve, reject) => {
      if (this.closed || !this.socket) {
        return reject(new Error('Not connected to hub.'));
      }

      const timeoutId = setTimeout(() => {
        const idx = this.listPromises.indexOf(wrappedResolve);
        if (idx !== -1) {
          this.listPromises.splice(idx, 1);
          resolve([]);
        }
      }, 2000);

      const wrappedResolve = (clients) => {
        clearTimeout(timeoutId);
        resolve(clients);
      };

      this.listPromises.push(wrappedResolve);

      try {
        this.socket.write(JSON.stringify({ type: 'list' }) + '\n');
      } catch (err) {
        const idx = this.listPromises.indexOf(wrappedResolve);
        if (idx !== -1) {
          this.listPromises.splice(idx, 1);
        }
        clearTimeout(timeoutId);
        reject(err);
      }
    });
  }

  list_clients() {
    return this.listClients();
  }

  listen(callback, onReconnect) {
    if (typeof callback !== 'function') {
      throw new Error('callback must be a function.');
    }
    this.on('message', callback);
    if (onReconnect && typeof onReconnect === 'function') {
      this.on('reconnect', onReconnect);
    }
  }
}

const DEFAULT_LAN_REST_URL = 'http://127.0.0.1:50508';

function _lanHttpRequest(method, apiPath, body = null, baseUrl = DEFAULT_LAN_REST_URL) {
  return new Promise((resolve, reject) => {
    const url = new URL(apiPath, baseUrl);
    const payload = body !== null ? JSON.stringify(body) : null;
    const headers = { Accept: 'application/json' };
    if (payload !== null) {
      headers['Content-Type'] = 'application/json';
      headers['Content-Length'] = Buffer.byteLength(payload);
    }

    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port || 80,
        path: url.pathname + url.search,
        method,
        headers,
        timeout: 15000,
      },
      (res) => {
        let raw = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          raw += chunk;
        });
        res.on('end', () => {
          try {
            const parsed = raw ? JSON.parse(raw) : {};
            if (res.statusCode >= 400) {
              const err = new Error(parsed.error || `HTTP ${res.statusCode}`);
              err.statusCode = res.statusCode;
              return reject(err);
            }
            resolve(parsed);
          } catch (err) {
            reject(err);
          }
        });
      }
    );

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy(new Error('Request timed out'));
    });

    if (payload !== null) {
      req.write(payload);
    }
    req.end();
  });
}

function lanStatus(baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest('GET', '/api/lan/status', null, baseUrl);
}

function lanScan(options = {}, baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest('POST', '/api/lan/scan', options, baseUrl);
}

function lanConnect(ip, options = {}, baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest('POST', '/api/lan/connect', { ip, ...options }, baseUrl);
}

function lanSend(filePath, to, baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest('POST', '/api/lan/send', { file_path: filePath, to }, baseUrl);
}

function lanAudit(limit = 100, baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest('GET', `/api/lan/audit?limit=${encodeURIComponent(limit)}`, null, baseUrl);
}

function packNrv(sourcePath, outputPath, password, baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest(
    'POST',
    '/api/nrv/pack',
    { source_path: sourcePath, output_path: outputPath, password },
    baseUrl
  );
}

function unpackNrv(nrvPath, outputDir, password, baseUrl = DEFAULT_LAN_REST_URL) {
  return _lanHttpRequest(
    'POST',
    '/api/nrv/unpack',
    { nrv_path: nrvPath, output_dir: outputDir, password },
    baseUrl
  );
}

class NerveLanClient {
  constructor(baseUrl = DEFAULT_LAN_REST_URL) {
    this.baseUrl = baseUrl;
  }

  lanStatus() { return lanStatus(this.baseUrl); }
  lanScan(options = {}) { return lanScan(options, this.baseUrl); }
  lanConnect(ip, options = {}) { return lanConnect(ip, options, this.baseUrl); }
  lanSend(filePath, to) { return lanSend(filePath, to, this.baseUrl); }
  lanAudit(limit = 100) { return lanAudit(limit, this.baseUrl); }
  packNrv(sourcePath, outputPath, password) {
    return packNrv(sourcePath, outputPath, password, this.baseUrl);
  }
  unpackNrv(nrvPath, outputDir, password) {
    return unpackNrv(nrvPath, outputDir, password, this.baseUrl);
  }
}

module.exports = {
  NexusClient,
  NerveLanClient,
  loadExternalConfig,
  lanStatus,
  lanScan,
  lanConnect,
  lanSend,
  lanAudit,
  packNrv,
  unpackNrv,
};
