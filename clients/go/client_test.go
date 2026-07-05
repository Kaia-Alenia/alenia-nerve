package go_client

import "testing"

func TestConnect(t *testing.T) {
	client := NewNexusClient()
	if !client.Connect("test_client") {
		t.Error("Failed to connect client")
	}
}
