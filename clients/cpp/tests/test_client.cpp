#include "nerve/nexus_client.hpp"
#include <iostream>
#include <thread>
#include <chrono>

int main() {
    std::cout << "Starting C++ Nerve Client Test..." << std::endl;
    
    nerve::NexusClient::Config cfg;
    cfg.use_tcp = true; // Use TCP for tests assuming Hub binds to TCP
    cfg.port = 50505;
    
    nerve::NexusClient client(cfg);
    
    bool received = false;
    
    client.listen("message", [&](const std::string& type, const nerve::json& payload) {
        std::cout << "Received message: " << payload.dump() << std::endl;
        received = true;
    });
    
    client.connect("cpp_test_client");
    
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    nerve::json data;
    data["hello"] = "world";
    client.broadcast(data);
    
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    client.disconnect();
    
    if (received) {
        std::cout << "Test passed!" << std::endl;
        return 0;
    } else {
        std::cout << "Test failed (or hub not running/no broadcast received)." << std::endl;
        return 1;
    }
}
