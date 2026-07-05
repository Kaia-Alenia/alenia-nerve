package go_client

type NexusClient struct {
	ClientID string
}

func NewNexusClient() *NexusClient {
	return &NexusClient{}
}

func (c *NexusClient) Connect(clientID string) bool {
	c.ClientID = clientID
	return true
}
