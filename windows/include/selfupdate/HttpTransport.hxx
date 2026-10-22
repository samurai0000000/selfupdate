/*
 * HttpTransport.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_HTTP_TRANSPORT_HXX
#define SELFUPDATE_HTTP_TRANSPORT_HXX

#include <atomic>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>

namespace selfupdate {

struct HttpResponse {
    int statusCode = 0;
    std::string body;
    std::map<std::string, std::string> headers;
    std::string errorMessage;

    bool isSuccess() const
    {
        return statusCode >= 200 && statusCode < 300;
    }
};

using StreamChunkCallback = std::function<bool(const void* chunk, size_t chunkSize, int64_t totalBytes)>;

class HttpTransport {
public:
    virtual ~HttpTransport() = default;

    virtual HttpResponse get(const std::string& url,
                             int connectTimeoutMs = 10000,
                             int readTimeoutMs = 10000,
                             const std::atomic<bool>* cancelFlag = nullptr) = 0;

    virtual bool downloadStream(const std::string& url,
                                StreamChunkCallback onChunk,
                                int connectTimeoutMs = 10000,
                                int readTimeoutMs = 30000,
                                const std::atomic<bool>* cancelFlag = nullptr,
                                std::string* outError = nullptr) = 0;

    static std::shared_ptr<HttpTransport> createDefault();
};

} // namespace selfupdate

#endif // SELFUPDATE_HTTP_TRANSPORT_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
