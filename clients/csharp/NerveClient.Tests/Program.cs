using System;
using System.Threading;
using Alenia.Nerve;
using Newtonsoft.Json.Linq;

namespace NerveClientTests
{
    class Program
    {
        static void Main(string[] args)
        {
            Console.WriteLine("Starting C# Nerve Client Test...");

            var config = new NexusClientConfig
            {
                UseTcp = true,
                Port = 50505
            };

            using var client = new NexusClient(config);

            bool received = false;
            client.Listen("message", (type, payload) =>
            {
                Console.WriteLine($"Received message: {payload.ToString(Newtonsoft.Json.Formatting.None)}");
                received = true;
            });

            client.Connect("csharp_test_client");

            Thread.Sleep(1000);

            var data = new JObject
            {
                ["hello"] = "from_csharp"
            };
            client.Broadcast(data);

            Thread.Sleep(2000);

            if (received)
            {
                Console.WriteLine("Test passed!");
                Environment.Exit(0);
            }
            else
            {
                Console.WriteLine("Test failed (or hub not running).");
                Environment.Exit(1);
            }
        }
    }
}
