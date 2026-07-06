#include "nerve/nexus_client.hpp"
#include <iostream>

#ifdef _WIN32
#define NERVE_USE_TCP 1
#else
#define NERVE_USE_TCP 0
#endif

namespace nerve {

NexusClient::NexusClient(Config cfg) : config_(std::move(cfg)) {
#if NERVE_USE_TCP
    config_.use_tcp = true; // Force TCP on Windows
#endif
}

NexusClient::~NexusClient() {
    disconnect();
}

void NexusClient::connect(const std::string& client_id) {
    client_id_ = client_id;
    closed_ = false;

    do_connect();

    io_thread_ = std::thread([this]() {
        while (!closed_) {
            try {
                io_context_.run();
                if (!closed_) {
                    std::this_thread::sleep_for(std::chrono::seconds(2));
                    io_context_.restart();
                    do_connect();
                }
            } catch (const std::exception& e) {
                std::cerr << "[NERVE C++] IO Error: " << e.what() << std::endl;
                if (!closed_) {
                    std::this_thread::sleep_for(std::chrono::seconds(2));
                    io_context_.restart();
                    do_connect();
                }
            }
        }
    });
}

void NexusClient::do_connect() {
    if (closed_) return;

    socket_ = std::make_unique<asio::generic::stream_protocol::socket>(io_context_);

    std::error_code ec;
    if (config_.use_tcp) {
        asio::ip::tcp::endpoint endpoint(asio::ip::make_address(config_.host), config_.port);
        socket_->connect(asio::generic::stream_protocol::endpoint(endpoint.protocol(), endpoint.data(), endpoint.size()), ec);
    } else {
        asio::local::stream_protocol::endpoint endpoint(config_.socket_path);
        socket_->connect(asio::generic::stream_protocol::endpoint(endpoint.protocol(), endpoint.data(), endpoint.size()), ec);
    }

    if (ec) {
        std::cerr << "[NERVE C++] Connection failed: " << ec.message() << std::endl;
        return;
    }

    connected_ = true;
    std::cout << "[NERVE C++] Connected to hub as '" << client_id_ << "'" << std::endl;

    json reg;
    reg["type"] = "register";
    reg["id"] = client_id_;
    if (!config_.auth_token.empty()) {
        reg["token"] = config_.auth_token;
    }

    do_write(reg.dump() + "\n");
    do_read();
}

void NexusClient::disconnect() {
    if (closed_) return;
    closed_ = true;
    connected_ = false;

    if (socket_) {
        std::error_code ec;
        socket_->close(ec);
    }
    io_context_.stop();

    if (io_thread_.joinable()) {
        io_thread_.join();
    }
}

void NexusClient::send(const std::string& to, const json& payload) {
    if (!connected_ || closed_) return;
    json msg;
    msg["type"] = "send";
    msg["to"] = to;
    msg["payload"] = payload;
    do_write(msg.dump() + "\n");
}

void NexusClient::broadcast(const json& payload) {
    if (!connected_ || closed_) return;
    json msg;
    msg["type"] = "broadcast";
    msg["payload"] = payload;
    do_write(msg.dump() + "\n");
}

void NexusClient::listen(const std::string& event_type, MessageCallback callback) {
    std::lock_guard<std::mutex> lock(handlers_mutex_);
    handlers_[event_type].push_back(std::move(callback));
}

void NexusClient::do_write(const std::string& msg) {
    if (!socket_ || !socket_->is_open()) return;
    
    std::lock_guard<std::mutex> lock(write_mutex_);
    std::error_code ec;
    asio::write(*socket_, asio::buffer(msg), ec);
    if (ec) {
        std::cerr << "[NERVE C++] Write error: " << ec.message() << std::endl;
        connected_ = false;
        socket_->close(ec);
    }
}

void NexusClient::do_read() {
    if (!socket_ || !socket_->is_open()) return;

    asio::async_read_until(*socket_, read_buffer_, '\n',
        [this](std::error_code ec, std::size_t length) {
            if (!ec) {
                std::istream is(&read_buffer_);
                std::string line;
                std::getline(is, line);
                if (!line.empty() && line.back() == '\r') {
                    line.pop_back();
                }
                
                process_line(line);
                do_read();
            } else {
                std::cerr << "[NERVE C++] Read error: " << ec.message() << std::endl;
                connected_ = false;
                std::error_code ignore_ec;
                socket_->close(ignore_ec);
            }
        });
}

void NexusClient::process_line(const std::string& line) {
    try {
        json parsed = json::parse(line);
        std::string type = parsed.value("type", "");

        if (type == "ping") {
            json pong;
            pong["type"] = "pong";
            do_write(pong.dump() + "\n");
            return;
        }

        std::lock_guard<std::mutex> lock(handlers_mutex_);
        if (handlers_.count(type)) {
            for (auto& cb : handlers_[type]) {
                cb(type, parsed);
            }
        }
    } catch (const std::exception& e) {
        std::cerr << "[NERVE C++] JSON parsing error: " << e.what() << std::endl;
    }
}

} // namespace nerve
