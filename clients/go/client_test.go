package nerve

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net"
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
