// Package nerve provides a lightweight IPC client for the Alenia Nerve local
// socket engine. It supports Unix Domain Sockets (Linux/macOS) and TCP
// (Windows or explicit configuration).
//
// License: GNU General Public License v3 (GPL v3)
// Author:  Alenia Studios <contact.aleniastudios@gmail.com>
package nerve

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"runtime"
	"strings"
	"sync"
	"time"
)

// ConnectionMode controls the transport used by NexusClient.
type ConnectionMode int

const (
	// ModeAuto selects UDS on Linux/macOS, TCP on Windows.
	ModeAuto ConnectionMode = iota
	// ModeTCP forces TCP transport.
	ModeTCP
	// ModeUDS forces Unix Domain Socket transport.
	ModeUDS
)

// Config holds the optional configuration for NexusClient.
type Config struct {
	Host          string
	Port          int
	SocketPath    string
	AuthToken     string
	RetryInterval time.Duration
	Mode          ConnectionMode
}

func defaultConfig() Config {
	return Config{
		Host:          "127.0.0.1",
		Port:          50505,
		SocketPath:    "/tmp/nerve.sock",
		RetryInterval: 2 * time.Second,
		Mode:          ModeAuto,
	}
}

// loadFileConfig parses a nerve.config file (JSON or KEY=VALUE).
func loadFileConfig(path string) map[string]string {
	out := make(map[string]string)
	data, err := os.ReadFile(path)
	if err != nil {
		return out
	}

	// Try JSON first.
	var obj map[string]interface{}
	if json.Unmarshal(data, &obj) == nil {
		for k, v := range obj {
			out[k] = fmt.Sprintf("%v", v)
		}
		return out
	}

	// Fall back to KEY=VALUE.
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if idx := strings.IndexByte(line, '='); idx >= 0 {
			out[strings.TrimSpace(line[:idx])] = strings.TrimSpace(line[idx+1:])
		}
	}
	return out
}

// MessageHandler is a callback invoked for each incoming message.
type MessageHandler func(msg map[string]interface{})

// NexusClient connects to an Alenia Nerve hub and handles bidirectional JSON
// message exchange over a persistent socket connection.
type NexusClient struct {
	cfg          Config
	clientID     string
	conn         net.Conn
	mu           sync.Mutex
	closed       bool
	handlers     []MessageHandler
	reconnectCbs []func()
}

// NewNexusClient creates a client with default configuration.
func NewNexusClient() *NexusClient {
	return &NexusClient{cfg: defaultConfig()}
}

// NewNexusClientFromConfig creates a client using the provided Config.
func NewNexusClientFromConfig(cfg Config) *NexusClient {
	base := defaultConfig()
	if cfg.Host != "" {
		base.Host = cfg.Host
	}
	if cfg.Port != 0 {
		base.Port = cfg.Port
	}
	if cfg.SocketPath != "" {
		base.SocketPath = cfg.SocketPath
	}
	if cfg.AuthToken != "" {
		base.AuthToken = cfg.AuthToken
	}
	if cfg.RetryInterval > 0 {
		base.RetryInterval = cfg.RetryInterval
	}
	if cfg.Mode != ModeAuto {
		base.Mode = cfg.Mode
	}
	return &NexusClient{cfg: base}
}

// NewNexusClientFromFile creates a client loading settings from a config file.
func NewNexusClientFromFile(path string) *NexusClient {
	raw := loadFileConfig(path)
	cfg := defaultConfig()
	if v, ok := raw["host"]; ok {
		cfg.Host = v
	}
	if v, ok := raw["port"]; ok {
		var p int
		fmt.Sscanf(v, "%d", &p)
		if p > 0 {
			cfg.Port = p
		}
	}
	if v, ok := raw["socket_path"]; ok {
		cfg.SocketPath = v
	} else if v, ok := raw["socketPath"]; ok {
		cfg.SocketPath = v
	}
	if v, ok := raw["auth_token"]; ok {
		cfg.AuthToken = v
	} else if v, ok := raw["authToken"]; ok {
		cfg.AuthToken = v
	}
	return &NexusClient{cfg: cfg}
}

func (c *NexusClient) dial() (net.Conn, error) {
	useTCP := c.cfg.Mode == ModeTCP || (c.cfg.Mode == ModeAuto && runtime.GOOS == "windows")
	if useTCP {
		addr := net.JoinHostPort(c.cfg.Host, fmt.Sprintf("%d", c.cfg.Port))
		return net.DialTimeout("tcp", addr, 5*time.Second)
	}
	return net.DialTimeout("unix", c.cfg.SocketPath, 5*time.Second)
}

// Connect registers the client with the hub under clientID.
// It blocks until the handshake is complete or a non-retryable error occurs.
func (c *NexusClient) Connect(clientID string) error {
	c.clientID = clientID
	c.mu.Lock()
	c.closed = false
	c.mu.Unlock()

	return c.connectLoop(true)
}

func (c *NexusClient) connectLoop(firstAttempt bool) error {
	for {
		c.mu.Lock()
		if c.closed {
			c.mu.Unlock()
			return fmt.Errorf("client closed")
		}
		c.mu.Unlock()

		conn, err := c.dial()
		if err != nil {
			if firstAttempt {
				return fmt.Errorf("nerve: dial failed: %w", err)
			}
			time.Sleep(c.cfg.RetryInterval)
			continue
		}

		reg := map[string]interface{}{"type": "register", "id": c.clientID}
		if c.cfg.AuthToken != "" {
			reg["token"] = c.cfg.AuthToken
		}
		line, _ := json.Marshal(reg)

		if _, err := fmt.Fprintf(conn, "%s\n", line); err != nil {
			conn.Close()
			if firstAttempt {
				return err
			}
			time.Sleep(c.cfg.RetryInterval)
			continue
		}

		// Read handshake response.
		scanner := bufio.NewScanner(conn)
		if !scanner.Scan() {
			conn.Close()
			if firstAttempt {
				return fmt.Errorf("nerve: handshake: no response")
			}
			time.Sleep(c.cfg.RetryInterval)
			continue
		}
		var resp map[string]interface{}
		if err := json.Unmarshal(scanner.Bytes(), &resp); err != nil {
			conn.Close()
			if firstAttempt {
				return err
			}
			continue
		}

		if resp["type"] == "registered" && resp["status"] == "success" {
			c.mu.Lock()
			c.conn = conn
			c.mu.Unlock()

			if !firstAttempt {
				for _, cb := range c.reconnectCbs {
					go cb()
				}
			}

			go c.readLoop(scanner, conn)
			return nil
		}

		if resp["status"] == "failed" && resp["reason"] == "auth" {
			conn.Close()
			return fmt.Errorf("nerve: authentication failed")
		}

		conn.Close()
		return fmt.Errorf("nerve: unexpected handshake response: %v", resp)
	}
}

func (c *NexusClient) readLoop(scanner *bufio.Scanner, conn net.Conn) {
	for scanner.Scan() {
		var msg map[string]interface{}
		if err := json.Unmarshal(scanner.Bytes(), &msg); err != nil {
			continue
		}
		t, _ := msg["type"].(string)
		if t == "ping" || t == "pong" {
			continue
		}
		c.mu.Lock()
		hs := make([]MessageHandler, len(c.handlers))
		copy(hs, c.handlers)
		c.mu.Unlock()
		for _, h := range hs {
			h(msg)
		}
	}

	// Connection lost — attempt reconnect unless closed.
	c.mu.Lock()
	closed := c.closed
	c.conn = nil
	c.mu.Unlock()
	conn.Close()

	if !closed {
		time.Sleep(c.cfg.RetryInterval)
		_ = c.connectLoop(false)
	}
}

// Disconnect closes the connection cleanly.
func (c *NexusClient) Disconnect() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.closed = true
	if c.conn != nil {
		c.conn.Close()
		c.conn = nil
	}
}

// Send delivers a message to a specific client registered on the hub.
func (c *NexusClient) Send(to string, payload interface{}) error {
	return c.writeJSON(map[string]interface{}{"type": "send", "to": to, "payload": payload})
}

// Broadcast delivers a message to all connected clients.
func (c *NexusClient) Broadcast(payload interface{}) error {
	return c.writeJSON(map[string]interface{}{"type": "broadcast", "payload": payload})
}

// ListClients requests the list of connected client IDs from the hub.
func (c *NexusClient) ListClients() ([]string, error) {
	if err := c.writeJSON(map[string]interface{}{"type": "list"}); err != nil {
		return nil, err
	}
	return nil, nil
}

// Listen registers a callback invoked for every incoming message.
func (c *NexusClient) Listen(handler MessageHandler) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.handlers = append(c.handlers, handler)
}

// OnReconnect registers a callback invoked after a successful reconnection.
func (c *NexusClient) OnReconnect(cb func()) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.reconnectCbs = append(c.reconnectCbs, cb)
}

func (c *NexusClient) writeJSON(v interface{}) error {
	c.mu.Lock()
	conn := c.conn
	c.mu.Unlock()
	if conn == nil {
		return fmt.Errorf("nerve: not connected")
	}
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(conn, "%s\n", data)
	return err
}
