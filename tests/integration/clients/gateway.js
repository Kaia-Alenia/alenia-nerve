const { NexusClient } = require('../../../clients/javascript/index.js');

const client = new NexusClient();

client.connect('api_gateway').then(() => {
    client.listen((msg) => {
        // msg is the full message: {"type": ..., "from": ..., "payload": {...}}
        const data = msg && msg.payload;
        if (!data) return;

        if (data.type === 'task_result') {
            console.log('\n[API Gateway] Tarea completada recibida de Python:');
            console.log(`  -> Tarea ID: ${data.task_id}`);
            console.log('  -> Resultado:', data.result);
        }
    });
    console.log('[API Gateway] Iniciado. Simulando interfaz de usuario (ej. Electron)...');
}).catch(console.error);

let taskId = 1;
setInterval(() => {
    const task = {
        type: 'process_task',
        task_id: taskId,
        payload: `imagen_base_${taskId}.png`,
        operations: ['remove_background', 'upscale_4x'],
    };

    console.log(`\n[API Gateway] Enviando peticion de IA al backend (ID: ${taskId})...`);
    client.send('python_worker', task);

    taskId++;
}, 4000);
