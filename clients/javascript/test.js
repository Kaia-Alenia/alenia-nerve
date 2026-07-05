const assert = require('assert');
const { NexusClient } = require('./index');

try {
  const client = new NexusClient();
  assert.strictEqual(client.connect('test_client'), true);
  console.log('JavaScript client tests passed successfully.');
  process.exit(0);
} catch (error) {
  console.error('JavaScript client tests failed:', error);
  process.exit(1);
}
