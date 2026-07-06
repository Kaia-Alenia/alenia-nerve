const { NexusClient } = require('../../../clients/javascript/index.js');

const client = new NexusClient();

client.on('reconnect', (attempt) => {
    console.log(`[JS] Reconnecting... (Attempt ${attempt})`);
});

client.connect('js_client').then(() => {
    client.listen((msg) => {
        // msg is the full message: {"type": ..., "from": ..., "payload": {...}}
        const payload = msg && msg.payload;
        if (!payload) return;

        if (payload.event === 'ping') {
            console.log(`[JS] Received ping from ${msg.from || 'unknown'}, sending pong...`);
            // Echo timestamp back to calculate latency
            client.broadcast({
                event: 'pong',
                from: 'js_client',
                timestamp: payload.timestamp,
            });
        } else if (payload.event === 'pong') {
            console.log(`[JS] Received pong from ${payload.from}`);
        }
    });
}).catch(console.error);

// Keep alive until terminated by the test harness.
setInterval(() => {}, 1000);
