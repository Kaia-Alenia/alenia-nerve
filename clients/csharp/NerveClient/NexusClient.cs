using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace Alenia.Nerve
{
    public class NexusClientConfig
    {
        public string SocketPath { get; set; } = "/tmp/nerve.sock";
        public string Host { get; set; } = "127.0.0.1";
        public int Port { get; set; } = 50505;
        public string AuthToken { get; set; } = "";
        public bool UseTcp { get; set; } = false;
    }

    public class NexusClient : IDisposable
    {
        private readonly NexusClientConfig _config;
        private string _clientId = string.Empty;
        private Socket? _socket;
        private Stream? _stream;
        private StreamReader? _reader;
        private StreamWriter? _writer;
        
        private bool _connected;
        private bool _closed = true;
        private readonly SemaphoreSlim _writeLock = new SemaphoreSlim(1, 1);
        private Thread? _receiveThread;

        private readonly Dictionary<string, List<Action<string, JObject>>> _handlers = new();
        private readonly object _handlersLock = new object();

        public NexusClient(NexusClientConfig config)
        {
            _config = config;
            
            // Auto force TCP on Windows if not already set, since UDS paths like /tmp/nerve.sock won't work easily
            if (Environment.OSVersion.Platform == PlatformID.Win32NT)
            {
                _config.UseTcp = true;
            }
        }

        public void Connect(string clientId)
        {
            _clientId = clientId;
            _closed = false;

            DoConnect();

            _receiveThread = new Thread(ReceiveLoop) { IsBackground = true };
            _receiveThread.Start();
        }

        private void DoConnect()
        {
            if (_closed) return;

            try
            {
                if (_config.UseTcp)
                {
                    _socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
                    _socket.Connect(_config.Host, _config.Port);
                }
                else
                {
                    _socket = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
                    _socket.Connect(new UnixDomainSocketEndPoint(_config.SocketPath));
                }

                _stream = new NetworkStream(_socket);
                _reader = new StreamReader(_stream, Encoding.UTF8);
                _writer = new StreamWriter(_stream, Encoding.UTF8) { AutoFlush = true };

                _connected = true;
                Console.WriteLine($"[NERVE C#] Connected to hub as '{_clientId}'");

                var regMsg = new JObject
                {
                    ["type"] = "register",
                    ["id"] = _clientId
                };
                if (!string.IsNullOrEmpty(_config.AuthToken))
                {
                    regMsg["token"] = _config.AuthToken;
                }

                DoWrite(regMsg.ToString(Formatting.None) + "\n");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[NERVE C#] Connection failed: {ex.Message}");
                _connected = false;
            }
        }

        private void ReceiveLoop()
        {
            while (!_closed)
            {
                try
                {
                    if (_connected && _reader != null)
                    {
                        string? line = _reader.ReadLine();
                        if (line == null)
                        {
                            throw new IOException("Socket closed");
                        }
                        ProcessLine(line);
                    }
                    else
                    {
                        Thread.Sleep(2000);
                        DoConnect();
                    }
                }
                catch (Exception ex)
                {
                    if (!_closed)
                    {
                        Console.WriteLine($"[NERVE C#] Disconnected: {ex.Message}");
                        _connected = false;
                        Thread.Sleep(2000);
                        DoConnect();
                    }
                }
            }
        }

        private void ProcessLine(string line)
        {
            try
            {
                var parsed = JObject.Parse(line);
                var type = parsed["type"]?.ToString() ?? "";

                if (type == "ping")
                {
                    var pong = new JObject { ["type"] = "pong" };
                    DoWrite(pong.ToString(Formatting.None) + "\n");
                    return;
                }

                lock (_handlersLock)
                {
                    if (_handlers.TryGetValue(type, out var list))
                    {
                        foreach (var cb in list)
                        {
                            // Invoke handlers asynchronously to prevent blocking the read loop
                            Task.Run(() => cb(type, parsed));
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[NERVE C#] JSON parsing error: {ex.Message}");
            }
        }

        private void DoWrite(string msg)
        {
            if (!_connected || _writer == null) return;

            _writeLock.Wait();
            try
            {
                _writer.Write(msg);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[NERVE C#] Write error: {ex.Message}");
                _connected = false;
            }
            finally
            {
                _writeLock.Release();
            }
        }

        public void Send(string to, JObject payload)
        {
            if (!_connected || _closed) return;
            var msg = new JObject
            {
                ["type"] = "send",
                ["to"] = to,
                ["payload"] = payload
            };
            DoWrite(msg.ToString(Formatting.None) + "\n");
        }

        public void Broadcast(JObject payload)
        {
            if (!_connected || _closed) return;
            var msg = new JObject
            {
                ["type"] = "broadcast",
                ["payload"] = payload
            };
            DoWrite(msg.ToString(Formatting.None) + "\n");
        }

        public void Listen(string eventType, Action<string, JObject> callback)
        {
            lock (_handlersLock)
            {
                if (!_handlers.ContainsKey(eventType))
                {
                    _handlers[eventType] = new List<Action<string, JObject>>();
                }
                _handlers[eventType].Add(callback);
            }
        }

        public void Disconnect()
        {
            if (_closed) return;
            _closed = true;
            _connected = false;

            try
            {
                _socket?.Close();
            }
            catch { }
        }

        public void Dispose()
        {
            Disconnect();
        }
    }
}
