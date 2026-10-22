/*
 * HttpTransport.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/HttpTransport.hxx"
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <vector>

#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>
#else
#include <arpa/inet.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#endif

namespace selfupdate {

namespace {

#if defined(_WIN32)

std::wstring toWide(const std::string& str)
{
    if (str.empty()) {
        return L"";
    }
    int len = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, nullptr, 0);
    if (len <= 0) {
        return L"";
    }
    std::vector<wchar_t> buf(len);
    MultiByteToWideChar(CP_UTF8, 0, str.c_str(), -1, buf.data(), len);
    return std::wstring(buf.data());
}

class WinHttpTransport : public HttpTransport {
public:
    HttpResponse get(const std::string& url,
                     int connectTimeoutMs,
                     int readTimeoutMs,
                     const std::atomic<bool>* cancelFlag) override
    {
        HttpResponse response;
        downloadStream(
            url,
            [&response](const void* chunk, size_t size, int64_t /*totalBytes*/) -> bool {
                response.body.append(reinterpret_cast<const char*>(chunk), size);
                return true;
            },
            connectTimeoutMs,
            readTimeoutMs,
            cancelFlag,
            &response.errorMessage);
        return response;
    }

    bool downloadStream(const std::string& url,
                        StreamChunkCallback onChunk,
                        int connectTimeoutMs,
                        int readTimeoutMs,
                        const std::atomic<bool>* cancelFlag,
                        std::string* outError) override
    {
        std::wstring currentUrl = toWide(url);
        int maxRedirects = 5;

        HINTERNET hSession = WinHttpOpen(
            L"selfupdate/1.0",
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME,
            WINHTTP_NO_PROXY_BYPASS,
            0);
        if (!hSession) {
            if (outError) {
                *outError = "WinHttpOpen failed with error " + std::to_string(GetLastError());
            }
            return false;
        }

        WinHttpSetTimeouts(hSession, connectTimeoutMs, connectTimeoutMs, readTimeoutMs, readTimeoutMs);

        bool success = false;
        for (int redirectCount = 0; redirectCount < maxRedirects; ++redirectCount) {
            if (cancelFlag && cancelFlag->load()) {
                if (outError) *outError = "Operation cancelled";
                WinHttpCloseHandle(hSession);
                return false;
            }

            URL_COMPONENTSW urlComp;
            std::memset(&urlComp, 0, sizeof(urlComp));
            urlComp.dwStructSize = sizeof(urlComp);
            urlComp.dwHostNameLength = static_cast<DWORD>(-1);
            urlComp.dwUrlPathLength = static_cast<DWORD>(-1);
            urlComp.dwExtraInfoLength = static_cast<DWORD>(-1);

            if (!WinHttpCrackUrl(currentUrl.c_str(), 0, 0, &urlComp)) {
                if (outError) *outError = "WinHttpCrackUrl failed for URL";
                WinHttpCloseHandle(hSession);
                return false;
            }

            std::wstring host(urlComp.lpszHostName, urlComp.dwHostNameLength);
            std::wstring path(urlComp.lpszUrlPath, urlComp.dwUrlPathLength);
            if (urlComp.dwExtraInfoLength > 0 && urlComp.lpszExtraInfo != nullptr) {
                path.append(urlComp.lpszExtraInfo, urlComp.dwExtraInfoLength);
            }
            if (path.empty()) {
                path = L"/";
            }

            HINTERNET hConnect = WinHttpConnect(hSession, host.c_str(), urlComp.nPort, 0);
            if (!hConnect) {
                if (outError) *outError = "WinHttpConnect failed: " + std::to_string(GetLastError());
                WinHttpCloseHandle(hSession);
                return false;
            }

            DWORD openFlags = 0;
            if (urlComp.nScheme == INTERNET_SCHEME_HTTPS) {
                openFlags |= WINHTTP_FLAG_SECURE;
            }
            openFlags |= WINHTTP_FLAG_REFRESH;

            HINTERNET hRequest = WinHttpOpenRequest(
                hConnect,
                L"GET",
                path.c_str(),
                nullptr,
                WINHTTP_NO_REFERER,
                WINHTTP_DEFAULT_ACCEPT_TYPES,
                openFlags);
            if (!hRequest) {
                if (outError) *outError = "WinHttpOpenRequest failed: " + std::to_string(GetLastError());
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                return false;
            }

            DWORD redirectPolicy = WINHTTP_OPTION_REDIRECT_POLICY_ALWAYS;
            WinHttpSetOption(hRequest, WINHTTP_OPTION_REDIRECT_POLICY, &redirectPolicy, sizeof(redirectPolicy));

            const wchar_t* noCacheHeader = L"Cache-Control: no-cache\r\nPragma: no-cache\r\n";
            WinHttpAddRequestHeaders(hRequest, noCacheHeader, static_cast<DWORD>(-1), WINHTTP_ADDREQ_FLAG_ADD);

            BOOL sent = WinHttpSendRequest(
                hRequest,
                WINHTTP_NO_ADDITIONAL_HEADERS,
                0,
                WINHTTP_NO_REQUEST_DATA,
                0,
                0,
                0);
            if (!sent) {
                if (outError) *outError = "WinHttpSendRequest failed: " + std::to_string(GetLastError());
                WinHttpCloseHandle(hRequest);
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                return false;
            }

            BOOL recvd = WinHttpReceiveResponse(hRequest, nullptr);
            if (!recvd) {
                if (outError) *outError = "WinHttpReceiveResponse failed: " + std::to_string(GetLastError());
                WinHttpCloseHandle(hRequest);
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                return false;
            }

            DWORD statusCode = 0;
            DWORD headerSize = sizeof(statusCode);
            WinHttpQueryHeaders(
                hRequest,
                WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                WINHTTP_HEADER_NAME_BY_INDEX,
                &statusCode,
                &headerSize,
                WINHTTP_NO_HEADER_INDEX);

            if (statusCode == 301 || statusCode == 302 || statusCode == 303 ||
                statusCode == 307 || statusCode == 308) {
                DWORD locSize = 0;
                WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_LOCATION, WINHTTP_HEADER_NAME_BY_INDEX, nullptr, &locSize, WINHTTP_NO_HEADER_INDEX);
                if (locSize > 0) {
                    std::vector<wchar_t> locBuf(locSize / sizeof(wchar_t) + 1);
                    if (WinHttpQueryHeaders(hRequest, WINHTTP_QUERY_LOCATION, WINHTTP_HEADER_NAME_BY_INDEX, locBuf.data(), &locSize, WINHTTP_NO_HEADER_INDEX)) {
                        currentUrl = locBuf.data();
                        WinHttpCloseHandle(hRequest);
                        WinHttpCloseHandle(hConnect);
                        continue;
                    }
                }
            }

            if (statusCode < 200 || statusCode >= 300) {
                if (outError) {
                    *outError = "HTTP server returned error status " + std::to_string(statusCode);
                }
                WinHttpCloseHandle(hRequest);
                WinHttpCloseHandle(hConnect);
                WinHttpCloseHandle(hSession);
                return false;
            }

            int64_t totalBytes = -1;
            DWORD contentLength = 0;
            DWORD clSize = sizeof(contentLength);
            if (WinHttpQueryHeaders(
                    hRequest,
                    WINHTTP_QUERY_CONTENT_LENGTH | WINHTTP_QUERY_FLAG_NUMBER,
                    WINHTTP_HEADER_NAME_BY_INDEX,
                    &contentLength,
                    &clSize,
                    WINHTTP_NO_HEADER_INDEX)) {
                totalBytes = static_cast<int64_t>(contentLength);
            }

            char buffer[16384];
            DWORD bytesRead = 0;
            bool streamAborted = false;
            while (true) {
                if (cancelFlag && cancelFlag->load()) {
                    if (outError) *outError = "Download cancelled";
                    streamAborted = true;
                    break;
                }

                DWORD bytesAvailable = 0;
                if (!WinHttpQueryDataAvailable(hRequest, &bytesAvailable)) {
                    if (outError) *outError = "WinHttpQueryDataAvailable failed: " + std::to_string(GetLastError());
                    streamAborted = true;
                    break;
                }
                if (bytesAvailable == 0) {
                    break;
                }

                DWORD toRead = (std::min)(bytesAvailable, static_cast<DWORD>(sizeof(buffer)));
                if (!WinHttpReadData(hRequest, buffer, toRead, &bytesRead)) {
                    if (outError) *outError = "WinHttpReadData failed: " + std::to_string(GetLastError());
                    streamAborted = true;
                    break;
                }
                if (bytesRead == 0) {
                    break;
                }

                if (onChunk && !onChunk(buffer, bytesRead, totalBytes)) {
                    if (outError) *outError = "Stream chunk callback requested abort";
                    streamAborted = true;
                    break;
                }
            }

            WinHttpCloseHandle(hRequest);
            WinHttpCloseHandle(hConnect);
            if (!streamAborted) {
                success = true;
            }
            break;
        }

        WinHttpCloseHandle(hSession);
        return success;
    }
};

#else

std::string toLower(const std::string& str)
{
    std::string out = str;
    for (char& c : out) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return out;
}

std::string trim(const std::string& str)
{
    size_t start = 0;
    while (start < str.size() && std::isspace(static_cast<unsigned char>(str[start]))) {
        start++;
    }
    if (start >= str.size()) {
        return "";
    }
    size_t end = str.size();
    while (end > start && std::isspace(static_cast<unsigned char>(str[end - 1]))) {
        end--;
    }
    return str.substr(start, end - start);
}

// POSIX socket-based HTTP client for Linux
struct ParsedUrl {
    bool isHttps = false;
    std::string host;
    int port = 80;
    std::string path = "/";
};

bool parseHttpUrl(const std::string& url, ParsedUrl* outParsed)
{
    if (url.rfind("http://", 0) == 0) {
        outParsed->isHttps = false;
        outParsed->port = 80;
        size_t afterScheme = 7;
        size_t slashPos = url.find('/', afterScheme);
        std::string hostPort = (slashPos != std::string::npos)
                                   ? url.substr(afterScheme, slashPos - afterScheme)
                                   : url.substr(afterScheme);
        outParsed->path = (slashPos != std::string::npos) ? url.substr(slashPos) : "/";

        size_t colonPos = hostPort.find(':');
        if (colonPos != std::string::npos) {
            outParsed->host = hostPort.substr(0, colonPos);
            outParsed->port = std::atoi(hostPort.substr(colonPos + 1).c_str());
        } else {
            outParsed->host = hostPort;
        }
        return true;
    }
    if (url.rfind("https://", 0) == 0) {
        outParsed->isHttps = true;
        outParsed->port = 443;
        size_t afterScheme = 8;
        size_t slashPos = url.find('/', afterScheme);
        std::string hostPort = (slashPos != std::string::npos)
                                   ? url.substr(afterScheme, slashPos - afterScheme)
                                   : url.substr(afterScheme);
        outParsed->path = (slashPos != std::string::npos) ? url.substr(slashPos) : "/";

        size_t colonPos = hostPort.find(':');
        if (colonPos != std::string::npos) {
            outParsed->host = hostPort.substr(0, colonPos);
            outParsed->port = std::atoi(hostPort.substr(colonPos + 1).c_str());
        } else {
            outParsed->host = hostPort;
        }
        return true;
    }
    return false;
}

class PosixHttpTransport : public HttpTransport {
public:
    HttpResponse get(const std::string& url,
                     int connectTimeoutMs,
                     int readTimeoutMs,
                     const std::atomic<bool>* cancelFlag) override
    {
        HttpResponse response;
        downloadStream(
            url,
            [&response](const void* chunk, size_t size, int64_t /*totalBytes*/) -> bool {
                response.body.append(reinterpret_cast<const char*>(chunk), size);
                return true;
            },
            connectTimeoutMs,
            readTimeoutMs,
            cancelFlag,
            &response.errorMessage,
            &response);
        return response;
    }

    bool downloadStream(const std::string& url,
                        StreamChunkCallback onChunk,
                        int connectTimeoutMs,
                        int readTimeoutMs,
                        const std::atomic<bool>* cancelFlag,
                        std::string* outError) override
    {
        return downloadStream(url, onChunk, connectTimeoutMs, readTimeoutMs, cancelFlag, outError, nullptr);
    }

private:
    bool downloadStream(const std::string& url,
                        StreamChunkCallback onChunk,
                        int connectTimeoutMs,
                        int readTimeoutMs,
                        const std::atomic<bool>* cancelFlag,
                        std::string* outError,
                        HttpResponse* outResponse)
    {
        std::string currentUrl = url;
        int maxRedirects = 5;

        for (int redirectCount = 0; redirectCount < maxRedirects; ++redirectCount) {
            if (cancelFlag && cancelFlag->load()) {
                if (outError) *outError = "Operation cancelled";
                if (outResponse) outResponse->statusCode = 0;
                return false;
            }

            ParsedUrl parsed;
            if (!parseHttpUrl(currentUrl, &parsed)) {
                if (outError) *outError = "Malformed URL: " + currentUrl;
                if (outResponse) outResponse->statusCode = 0;
                return false;
            }

            if (parsed.isHttps) {
                return executeCurlFallback(currentUrl, onChunk, connectTimeoutMs, readTimeoutMs, cancelFlag, outError, outResponse);
            }

            struct addrinfo hints;
            std::memset(&hints, 0, sizeof(hints));
            hints.ai_family = AF_UNSPEC;
            hints.ai_socktype = SOCK_STREAM;

            std::string portStr = std::to_string(parsed.port);
            struct addrinfo* resList = nullptr;
            int gaiErr = getaddrinfo(parsed.host.c_str(), portStr.c_str(), &hints, &resList);
            if (gaiErr != 0 || !resList) {
                if (outError) *outError = "DNS resolution failed: " + std::string(gai_strerror(gaiErr));
                if (outResponse) outResponse->statusCode = 0;
                return false;
            }

            int sock = -1;
            for (struct addrinfo* p = resList; p != nullptr; p = p->ai_next) {
                sock = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
                if (sock < 0) {
                    continue;
                }

                struct timeval tvConnect;
                tvConnect.tv_sec = connectTimeoutMs / 1000;
                tvConnect.tv_usec = (connectTimeoutMs % 1000) * 1000;
                setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tvConnect, sizeof(tvConnect));

                if (connect(sock, p->ai_addr, p->ai_addrlen) == 0) {
                    break;
                }
                close(sock);
                sock = -1;
            }
            freeaddrinfo(resList);

            if (sock < 0) {
                if (outError) *outError = "Connection failed to " + parsed.host + ":" + portStr;
                if (outResponse) outResponse->statusCode = 0;
                return false;
            }

            struct timeval tvRead;
            tvRead.tv_sec = readTimeoutMs / 1000;
            tvRead.tv_usec = (readTimeoutMs % 1000) * 1000;
            setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tvRead, sizeof(tvRead));
            setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tvRead, sizeof(tvRead));

            std::ostringstream req;
            req << "GET " << parsed.path << " HTTP/1.1\r\n";
            req << "Host: " << parsed.host;
            if ((!parsed.isHttps && parsed.port != 80) || (parsed.isHttps && parsed.port != 443)) {
                req << ":" << parsed.port;
            }
            req << "\r\n";
            req << "User-Agent: selfupdate/1.0\r\n";
            req << "Accept: */*\r\n";
            req << "Cache-Control: no-cache\r\n";
            req << "Connection: close\r\n\r\n";

            std::string reqStr = req.str();
            ssize_t sent = send(sock, reqStr.data(), reqStr.size(), 0);
            if (sent < 0 || static_cast<size_t>(sent) != reqStr.size()) {
                if (outError) *outError = "Failed to send HTTP request";
                close(sock);
                if (outResponse) outResponse->statusCode = 0;
                return false;
            }

            // Read response headers
            std::string headerBuf;
            char chunk[8192];
            size_t headerEnd = std::string::npos;
            while (headerEnd == std::string::npos) {
                if (cancelFlag && cancelFlag->load()) {
                    if (outError) *outError = "Download cancelled";
                    close(sock);
                    if (outResponse) outResponse->statusCode = 0;
                    return false;
                }
                ssize_t n = recv(sock, chunk, sizeof(chunk), 0);
                if (n <= 0) {
                    break;
                }
                headerBuf.append(chunk, static_cast<size_t>(n));
                headerEnd = headerBuf.find("\r\n\r\n");
            }

            if (headerEnd == std::string::npos) {
                if (outError) *outError = "Truncated HTTP headers from server";
                close(sock);
                if (outResponse) outResponse->statusCode = 0;
                return false;
            }

            std::string headersPart = headerBuf.substr(0, headerEnd);
            std::string bodyRemainder = headerBuf.substr(headerEnd + 4);

            std::istringstream hss(headersPart);
            std::string statusLine;
            std::getline(hss, statusLine);
            int statusCode = 0;
            std::istringstream slss(statusLine);
            std::string httpVer;
            slss >> httpVer >> statusCode;

            std::map<std::string, std::string> respHeaders;
            std::string line;
            while (std::getline(hss, line)) {
                if (!line.empty() && line.back() == '\r') {
                    line.pop_back();
                }
                size_t colon = line.find(':');
                if (colon != std::string::npos) {
                    std::string key = toLower(trim(line.substr(0, colon)));
                    std::string val = trim(line.substr(colon + 1));
                    respHeaders[key] = val;
                }
            }

            if (outResponse) {
                outResponse->statusCode = statusCode;
                outResponse->headers = respHeaders;
            }

            // Redirect handling
            if (statusCode == 301 || statusCode == 302 || statusCode == 303 ||
                statusCode == 307 || statusCode == 308) {
                auto itLoc = respHeaders.find("location");
                if (itLoc != respHeaders.end() && !itLoc->second.empty()) {
                    std::string nextUrl = itLoc->second;
                    if (nextUrl.rfind("/", 0) == 0) {
                        std::string scheme = parsed.isHttps ? "https://" : "http://";
                        nextUrl = scheme + parsed.host + nextUrl;
                    }
                    currentUrl = nextUrl;
                    close(sock);
                    continue;
                }
            }

            if (statusCode < 200 || statusCode >= 300) {
                if (outError) {
                    *outError = "HTTP server returned error status " + std::to_string(statusCode);
                }
                close(sock);
                return false;
            }

            int64_t totalBytes = -1;
            auto itCl = respHeaders.find("content-length");
            if (itCl != respHeaders.end()) {
                totalBytes = std::stoll(itCl->second);
            }

            bool isChunked = false;
            auto itTe = respHeaders.find("transfer-encoding");
            if (itTe != respHeaders.end() && itTe->second.find("chunked") != std::string::npos) {
                isChunked = true;
            }

            if (isChunked) {
                // Read and decode chunked stream
                std::string pending = bodyRemainder;
                bool done = false;
                while (!done) {
                    while (true) {
                        size_t crlf = pending.find("\r\n");
                        if (crlf == std::string::npos) {
                            break;
                        }
                        std::string sizeHex = pending.substr(0, crlf);
                        size_t chunkSize = 0;
                        try {
                            chunkSize = std::stoul(sizeHex, nullptr, 16);
                        } catch (...) {
                            done = true;
                            break;
                        }
                        if (chunkSize == 0) {
                            done = true;
                            break;
                        }
                        if (pending.size() < crlf + 2 + chunkSize + 2) {
                            break;
                        }
                        const char* dataPtr = pending.data() + crlf + 2;
                        if (onChunk && !onChunk(dataPtr, chunkSize, totalBytes)) {
                            close(sock);
                            return false;
                        }
                        pending.erase(0, crlf + 2 + chunkSize + 2);
                    }
                    if (done) {
                        break;
                    }
                    ssize_t n = recv(sock, chunk, sizeof(chunk), 0);
                    if (n <= 0) {
                        break;
                    }
                    pending.append(chunk, static_cast<size_t>(n));
                }
            } else {
                if (!bodyRemainder.empty()) {
                    if (onChunk && !onChunk(bodyRemainder.data(), bodyRemainder.size(), totalBytes)) {
                        close(sock);
                        return false;
                    }
                }
                while (true) {
                    if (cancelFlag && cancelFlag->load()) {
                        if (outError) *outError = "Download cancelled";
                        close(sock);
                        return false;
                    }
                    ssize_t n = recv(sock, chunk, sizeof(chunk), 0);
                    if (n <= 0) {
                        break;
                    }
                    if (onChunk && !onChunk(chunk, static_cast<size_t>(n), totalBytes)) {
                        close(sock);
                        return false;
                    }
                }
            }

            close(sock);
            return true;
        }

        if (outError) *outError = "Exceeded maximum redirect count (5)";
        return false;
    }

    bool executeCurlFallback(const std::string& url,
                             StreamChunkCallback onChunk,
                             int connectTimeoutMs,
                             int readTimeoutMs,
                             const std::atomic<bool>* cancelFlag,
                             std::string* outError,
                             HttpResponse* outResponse)
    {
        // Sanitize URL for shell argument
        for (char c : url) {
            if (c == '"' || c == '`' || c == '$' || c == '\\' || c == '\n' || c == '\r') {
                if (outError) *outError = "Invalid character in URL for curl invocation";
                return false;
            }
        }

        int connectSec = (connectTimeoutMs + 999) / 1000;
        int maxSec = (readTimeoutMs + 999) / 1000;
        if (connectSec < 1) connectSec = 1;
        if (maxSec < 1) maxSec = 1;

        std::string cmd = "curl -fsSL --connect-timeout " + std::to_string(connectSec) +
                          " -m " + std::to_string(maxSec) +
                          " --no-buffer \"" + url + "\" 2>/dev/null";

        FILE* fp = popen(cmd.c_str(), "r");
        if (!fp) {
            if (outError) *outError = "Failed to spawn curl for https request";
            return false;
        }

        char buffer[16384];
        bool ok = true;
        while (!feof(fp)) {
            if (cancelFlag && cancelFlag->load()) {
                if (outError) *outError = "Download cancelled";
                ok = false;
                break;
            }
            size_t bytes = fread(buffer, 1, sizeof(buffer), fp);
            if (bytes > 0) {
                if (onChunk && !onChunk(buffer, bytes, -1)) {
                    ok = false;
                    break;
                }
            }
        }
        int status = pclose(fp);
        if (status != 0 && ok) {
            if (outError) *outError = "curl exited with status " + std::to_string(status);
            if (outResponse) outResponse->statusCode = 500;
            return false;
        }
        if (outResponse) {
            outResponse->statusCode = 200;
        }
        return ok;
    }
};

#endif

} // namespace

std::shared_ptr<HttpTransport> HttpTransport::createDefault()
{
#if defined(_WIN32)
    return std::make_shared<WinHttpTransport>();
#else
    return std::make_shared<PosixHttpTransport>();
#endif
}

} // namespace selfupdate

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
