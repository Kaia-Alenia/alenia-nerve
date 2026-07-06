const { NexusClient } = require('../../../clients/javascript/index.js');

const client = new NexusClient();

client.on('reconnect', (attempt) => {
    console.log(`[JS] Reconnecting... (Attempt ${attempt})`);
});

client.connect('js_client').then(() => {
    client.listen((payload) => {
        if (payload && payload.event === 'ping') {
            // Echo timestamp back to calculate latency
            client.broadcast({ 
                event: 'pong',
                from: 'js_client', 
                timestamp: payload.timestamp 
            });
        }
    });
}).catch(console.error);

// Keep alive
setInterval(() => {}, 1000);
