#pragma once

#include <string>
#include <functional>
#include <memory>
#include <map>
#include <thread>
#include <atomic>
#include <mutex>
#include <asio.hpp>
#include <nlohmann/json.hpp>

namespace nerve {

using json = nlohmann::json;

class NexusClient {
public:
    using MessageCallback = std::function<void(const std::string&, const json&)>;

    struct Config {
        std::string socket_path = "/tmp/nerve.sock";
        std::string host = "127.0.0.1";
        int port = 50505;
        std::string auth_token = "";
        bool use_tcp = false;
    };

    explicit NexusClient(Config cfg = Config());
    ~NexusClient();

    void connect(const std::string& client_id);
    void disconnect();

    void send(const std::string& to, const json& payload);
    void broadcast(const json& payload);
    void listen(const std::string& event_type, MessageCallback callback);

private:
    void do_read();
    void process_line(const std::string& line);
    void do_write(const std::string& msg);
    void do_connect();

    Config config_;
    std::string client_id_;
    asio::io_context io_context_;
    std::thread io_thread_;

    std::unique_ptr<asio::generic::stream_protocol::socket> socket_;

    asio::streambuf read_buffer_;
    std::atomic<bool> connected_{false};
    std::atomic<bool> closed_{true};

    std::mutex handlers_mutex_;
    std::map<std::string, std::vector<MessageCallback>> handlers_;

    std::mutex write_mutex_;
};

} // namespace nerve
