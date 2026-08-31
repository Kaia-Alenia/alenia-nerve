package nerve

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"testing"
	"time"
)

// startMockHub starts a minimal TCP server that handles a single register
// handshake and returns the address it is listening on.
func startMockHub(t *testing.T) string {
	t.Helper()
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("mock hub listen: %v", err)
	}
	t.Cleanup(func() { ln.Close() })

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		defer conn.Close()

		scanner := bufio.NewScanner(conn)
		if scanner.Scan() {
			var msg map[string]interface{}
			if json.Unmarshal(scanner.Bytes(), &msg) == nil {
				resp, _ := json.Marshal(map[string]interface{}{
					"type":   "registered",
					"status": "success",
				})
				fmt.Fprintf(conn, "%s\n", resp)
			}
		}
		// Keep connection open briefly so client can cleanly disconnect.
		time.Sleep(500 * time.Millisecond)
	}()

	return ln.Addr().String()
}

func TestConnect(t *testing.T) {
	addr := startMockHub(t)

	host, portStr, _ := net.SplitHostPort(addr)
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	client := NewNexusClientFromConfig(Config{
		Host:          host,
		Port:          port,
		RetryInterval: 100 * time.Millisecond,
		Mode:          ModeTCP,
	})

	if err := client.Connect("test_client"); err != nil {
		t.Fatalf("Connect: %v", err)
	}

	client.Disconnect()
}

func TestSend(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()

	received := make(chan map[string]interface{}, 1)

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		defer conn.Close()

		scanner := bufio.NewScanner(conn)
		// Read register
		if scanner.Scan() {
			resp, _ := json.Marshal(map[string]interface{}{
				"type": "registered", "status": "success",
			})
			fmt.Fprintf(conn, "%s\n", resp)
		}
		// Read send message
		if scanner.Scan() {
			var msg map[string]interface{}
			json.Unmarshal(scanner.Bytes(), &msg)
			received <- msg
		}
	}()

	host, portStr, _ := net.SplitHostPort(ln.Addr().String())
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	client := NewNexusClientFromConfig(Config{
		Host: host, Port: port,
		RetryInterval: 100 * time.Millisecond,
		Mode:          ModeTCP,
	})
	if err := client.Connect("sender"); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer client.Disconnect()

	if err := client.Send("target", "hello"); err != nil {
		t.Fatalf("Send: %v", err)
	}

	select {
	case msg := <-received:
		if msg["type"] != "send" {
			t.Errorf("expected type=send, got %v", msg["type"])
		}
		if msg["to"] != "target" {
			t.Errorf("expected to=target, got %v", msg["to"])
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for message")
	}
}

func TestListClientsError(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		// Close the server side connection immediately after handshake to simulate a dropped connection
		scanner := bufio.NewScanner(conn)
		if scanner.Scan() {
			resp, _ := json.Marshal(map[string]interface{}{
				"type":   "registered",
				"status": "success",
			})
			fmt.Fprintf(conn, "%s\n", resp)
		}
		conn.Close()
	}()

	host, portStr, _ := net.SplitHostPort(ln.Addr().String())
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	client := NewNexusClientFromConfig(Config{
		Host:          host,
		Port:          port,
		RetryInterval: 100 * time.Millisecond,
		Mode:          ModeTCP,
	})

	if err := client.Connect("test_client"); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer client.Disconnect()

	// Wait briefly to allow the server to close its end
	time.Sleep(100 * time.Millisecond)

	// Since the server closed the connection, attempting to write should return an error.
	// We might also test it directly by closing the client connection object to guarantee an error.
	client.mu.Lock()
	if client.conn != nil {
		client.conn.Close()
	}
	client.mu.Unlock()

	_, err = client.ListClients()
	if err == nil {
		t.Fatal("expected error calling ListClients on a closed connection")
	}
}

func TestListClientsError(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		// Close the server side connection immediately after handshake to simulate a dropped connection
		scanner := bufio.NewScanner(conn)
		if scanner.Scan() {
			resp, _ := json.Marshal(map[string]interface{}{
				"type":   "registered",
				"status": "success",
			})
			fmt.Fprintf(conn, "%s\n", resp)
		}
		conn.Close()
	}()

	host, portStr, _ := net.SplitHostPort(ln.Addr().String())
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	client := NewNexusClientFromConfig(Config{
		Host:          host,
		Port:          port,
		RetryInterval: 100 * time.Millisecond,
		Mode:          ModeTCP,
	})

	if err := client.Connect("test_client"); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer client.Disconnect()

	// Wait briefly to allow the server to close its end
	time.Sleep(100 * time.Millisecond)

	// Since the server closed the connection, attempting to write should return an error.
	// We might also test it directly by closing the client connection object to guarantee an error.
	client.mu.Lock()
	if client.conn != nil {
		client.conn.Close()
	}
	client.mu.Unlock()

	_, err = client.ListClients()
	if err == nil {
		t.Fatal("expected error calling ListClients on a closed connection")
	}
}

func TestListClientsError(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		// Close the server side connection immediately after handshake to simulate a dropped connection
		scanner := bufio.NewScanner(conn)
		if scanner.Scan() {
			resp, _ := json.Marshal(map[string]interface{}{
				"type":   "registered",
				"status": "success",
			})
			fmt.Fprintf(conn, "%s\n", resp)
		}
		conn.Close()
	}()

	host, portStr, _ := net.SplitHostPort(ln.Addr().String())
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	client := NewNexusClientFromConfig(Config{
		Host:          host,
		Port:          port,
		RetryInterval: 100 * time.Millisecond,
		Mode:          ModeTCP,
	})

	if err := client.Connect("test_client"); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer client.Disconnect()

	// Wait briefly to allow the server to close its end
	time.Sleep(100 * time.Millisecond)

	// Since the server closed the connection, attempting to write should return an error.
	// We might also test it directly by closing the client connection object to guarantee an error.
	client.mu.Lock()
	if client.conn != nil {
		client.conn.Close()
	}
	client.mu.Unlock()

	_, err = client.ListClients()
	if err == nil {
		t.Fatal("expected error calling ListClients on a closed connection")
	}
}

func TestListen(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	defer ln.Close()

	go func() {
		conn, err := ln.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		scanner := bufio.NewScanner(conn)
		if scanner.Scan() {
			resp, _ := json.Marshal(map[string]interface{}{
				"type": "registered", "status": "success",
			})
			fmt.Fprintf(conn, "%s\n", resp)
		}
		// Push a message to the client
		push, _ := json.Marshal(map[string]interface{}{
			"type":    "send",
			"from":    "server",
			"payload": "ping",
		})
		fmt.Fprintf(conn, "%s\n", push)
		time.Sleep(500 * time.Millisecond)
	}()

	host, portStr, _ := net.SplitHostPort(ln.Addr().String())
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	client := NewNexusClientFromConfig(Config{
		Host: host, Port: port,
		RetryInterval: 100 * time.Millisecond,
		Mode:          ModeTCP,
	})

	got := make(chan map[string]interface{}, 1)
	client.Listen(func(msg map[string]interface{}) {
		got <- msg
	})

	if err := client.Connect("listener"); err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer client.Disconnect()

	select {
	case msg := <-got:
		if msg["payload"] != "ping" {
			t.Errorf("expected payload=ping, got %v", msg["payload"])
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timeout waiting for pushed message")
	}
}

func TestLoadFileConfig(t *testing.T) {
	// Test 1: File doesn't exist
	res := loadFileConfig("nonexistent_file.cfg")
	if len(res) != 0 {
		t.Errorf("Expected empty map for missing file, got %v", res)
	}

	// Test 2: JSON file
	jsonContent := []byte(`{"host": "127.0.0.1", "port": 50505, "use_ssl": true}`)
	jsonFile, err := os.CreateTemp("", "nerve_json_test_*.config")
	if err != nil {
		t.Fatalf("Failed to create temp json file: %v", err)
	}
	defer os.Remove(jsonFile.Name())
	
	if _, err := jsonFile.Write(jsonContent); err != nil {
		t.Fatalf("Failed to write temp json file: %v", err)
	}
	jsonFile.Close()

	jsonRes := loadFileConfig(jsonFile.Name())
	if jsonRes["host"] != "127.0.0.1" {
		t.Errorf("Expected host to be '127.0.0.1', got %v", jsonRes["host"])
	}
	if jsonRes["port"] != "50505" {
		t.Errorf("Expected port to be '50505', got %v", jsonRes["port"])
	}
	if jsonRes["use_ssl"] != "true" {
		t.Errorf("Expected use_ssl to be 'true', got %v", jsonRes["use_ssl"])
	}

	// Test 3: KEY=VALUE file
	kvContent := []byte(`
# This is a comment
host=192.168.1.10
port = 12345 

   # Another comment
use_ssl=false
	`)
	kvFile, err := os.CreateTemp("", "nerve_kv_test_*.config")
	if err != nil {
		t.Fatalf("Failed to create temp kv file: %v", err)
	}
	defer os.Remove(kvFile.Name())

	if _, err := kvFile.Write(kvContent); err != nil {
		t.Fatalf("Failed to write temp kv file: %v", err)
	}
	kvFile.Close()

	kvRes := loadFileConfig(kvFile.Name())
	if kvRes["host"] != "192.168.1.10" {
		t.Errorf("Expected host to be '192.168.1.10', got %v", kvRes["host"])
	}
	if kvRes["port"] != "12345" {
		t.Errorf("Expected port to be '12345', got %v", kvRes["port"])
	}
	if kvRes["use_ssl"] != "false" {
		t.Errorf("Expected use_ssl to be 'false', got %v", kvRes["use_ssl"])
	}
}

func TestNewNexusClientFromConfig(t *testing.T) {
	// Test with empty config (should use defaults where applicable)
	emptyCfg := Config{}
	clientEmpty := NewNexusClientFromConfig(emptyCfg)
	
	if clientEmpty.cfg.Host != "127.0.0.1" {
		t.Errorf("expected Host=127.0.0.1, got %v", clientEmpty.cfg.Host)
	}
	if clientEmpty.cfg.Port != 50505 {
		t.Errorf("expected Port=50505, got %v", clientEmpty.cfg.Port)
	}
	if clientEmpty.cfg.SocketPath != "/tmp/nerve.sock" {
		t.Errorf("expected SocketPath=/tmp/nerve.sock, got %v", clientEmpty.cfg.SocketPath)
	}
	if clientEmpty.cfg.RetryInterval != 2*time.Second {
		t.Errorf("expected RetryInterval=2s, got %v", clientEmpty.cfg.RetryInterval)
	}
	if clientEmpty.cfg.Mode != ModeAuto {
		t.Errorf("expected Mode=ModeAuto, got %v", clientEmpty.cfg.Mode)
	}
	if clientEmpty.cfg.UseSSL != false {
		t.Errorf("expected UseSSL=false, got %v", clientEmpty.cfg.UseSSL)
	}
	if clientEmpty.cfg.SSLInsecure != false {
		t.Errorf("expected SSLInsecure=false, got %v", clientEmpty.cfg.SSLInsecure)
	}

	// Test with fully populated config (should override all defaults)
	fullCfg := Config{
		Host:          "192.168.1.1",
		Port:          8080,
		SocketPath:    "/var/run/nerve.sock",
		AuthToken:     "secret-token",
		RetryInterval: 5 * time.Second,
		Mode:          ModeTCP,
		UseSSL:        true,
		SSLInsecure:   true,
	}
	clientFull := NewNexusClientFromConfig(fullCfg)

	if clientFull.cfg.Host != "192.168.1.1" {
		t.Errorf("expected Host=192.168.1.1, got %v", clientFull.cfg.Host)
	}
	if clientFull.cfg.Port != 8080 {
		t.Errorf("expected Port=8080, got %v", clientFull.cfg.Port)
	}
	if clientFull.cfg.SocketPath != "/var/run/nerve.sock" {
		t.Errorf("expected SocketPath=/var/run/nerve.sock, got %v", clientFull.cfg.SocketPath)
	}
	if clientFull.cfg.AuthToken != "secret-token" {
		t.Errorf("expected AuthToken=secret-token, got %v", clientFull.cfg.AuthToken)
	}
	if clientFull.cfg.RetryInterval != 5*time.Second {
		t.Errorf("expected RetryInterval=5s, got %v", clientFull.cfg.RetryInterval)
	}
	if clientFull.cfg.Mode != ModeTCP {
		t.Errorf("expected Mode=ModeTCP, got %v", clientFull.cfg.Mode)
	}
	if clientFull.cfg.UseSSL != true {
		t.Errorf("expected UseSSL=true, got %v", clientFull.cfg.UseSSL)
	}
	if clientFull.cfg.SSLInsecure != true {
		t.Errorf("expected SSLInsecure=true, got %v", clientFull.cfg.SSLInsecure)
	}
}
