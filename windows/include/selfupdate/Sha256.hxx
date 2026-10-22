/*
 * Sha256.hxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#ifndef SELFUPDATE_SHA256_HXX
#define SELFUPDATE_SHA256_HXX

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace selfupdate {

class Sha256 {
public:
    Sha256();
    ~Sha256() = default;

    void reset();
    void update(const void* data, size_t len);
    std::string finalHex();
    std::vector<uint8_t> finalBytes();

    static std::string hashBytes(const void* data, size_t len);
    static std::string hashString(const std::string& str);
    static std::string hashHex(const std::string& str) { return hashString(str); }
    static std::string hashHex(const void* data, size_t len) { return hashBytes(data, len); }
    static std::string hashFile(const std::string& path);

private:
    void transform(const uint8_t block[64]);

    uint32_t _state[8];
    uint64_t _bitCount;
    uint8_t _buffer[64];
    size_t _bufferLen;
    bool _finalized;
    std::string _hexResult;
};

} // namespace selfupdate

#endif // SELFUPDATE_SHA256_HXX

/*
 * Local variables:
 * mode: C++
 * c-file-style: "BSD"
 * c-basic-offset: 4
 * tab-width: 4
 * indent-tabs-mode: nil
 * End:
 */
