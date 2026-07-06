package main

import (
	"log"
	"time"
	nerve "github.com/Kaia-Alenia/alenia-nerve/go"
)

func main() {
	client := nerve.NewNexusClient()
	
	err := client.Connect("go_client")
	if err != nil {
		log.Fatalf("Failed to connect: %v", err)
	}
	defer client.Disconnect()

	client.Listen(func(payload map[string]interface{}) {
		event, eventOk := payload["event"].(string)
		if eventOk && event == "ping" {
			timestamp, ok := payload["timestamp"].(float64)
			if ok {
				pongPayload := map[string]interface{}{
					"event":     "pong",
					"from":      "go_client",
					"timestamp": timestamp,
				}
				client.Broadcast(pongPayload)
			}
		}
	})

	// Keep alive
	for {
		time.Sleep(1 * time.Second)
	}
}
