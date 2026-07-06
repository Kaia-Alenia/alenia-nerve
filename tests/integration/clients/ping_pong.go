package main

import (
	"log"
	"os"
	"os/signal"
	"syscall"
	nerve "github.com/Kaia-Alenia/alenia-nerve/go"
)

func main() {
	client := nerve.NewNexusClient()

	// Register listener BEFORE connecting so no messages are missed.
	client.Listen(func(payload map[string]interface{}) {
		inner, ok := payload["payload"]
		if !ok {
			return
		}
		msg, ok := inner.(map[string]interface{})
		if !ok {
			return
		}
		event, _ := msg["event"].(string)
		if event != "ping" {
			return
		}
		timestamp, ok := msg["timestamp"].(float64)
		if !ok {
			return
		}
		log.Printf("[GO] Received ping, sending pong...")
		pong := map[string]interface{}{
			"event":     "pong",
			"from":      "go_client",
			"timestamp": timestamp,
		}
		if err := client.Broadcast(pong); err != nil {
			log.Printf("[GO] Broadcast error: %v", err)
		}
	})

	if err := client.Connect("go_client"); err != nil {
		log.Fatalf("[GO] Failed to connect: %v", err)
	}
	defer client.Disconnect()
	log.Printf("[GO] Connected. Waiting for pings...")

	// Wait for SIGTERM/SIGINT sent by the test harness.
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)
	<-quit
	log.Printf("[GO] Shutting down.")
}
