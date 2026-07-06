cmake_minimum_required(VERSION 3.14)
project(NerveClient VERSION 1.3.8 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

# nlohmann/json
FetchContent_Declare(json
    URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
)
FetchContent_MakeAvailable(json)

# asio (standalone)
FetchContent_Declare(
  asio
  GIT_REPOSITORY https://github.com/chriskohlhoff/asio.git
  GIT_TAG        asio-1-28-0
)
FetchContent_GetProperties(asio)
if(NOT asio_POPULATED)
  FetchContent_Populate(asio)
  add_library(asio INTERFACE)
  target_include_directories(asio INTERFACE ${asio_SOURCE_DIR}/asio/include)
  target_compile_definitions(asio INTERFACE ASIO_STANDALONE ASIO_NO_DEPRECATED)
endif()

add_library(nerve_client
    src/nexus_client.cpp
)

target_include_directories(nerve_client
    PUBLIC 
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

target_link_libraries(nerve_client
    PUBLIC
        asio
        nlohmann_json::nlohmann_json
)

# Tests
enable_testing()
add_executable(test_client tests/test_client.cpp)
target_link_libraries(test_client nerve_client pthread)
add_test(NAME test_client COMMAND test_client)
