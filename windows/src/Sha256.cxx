/*
 * Sha256.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/Sha256.hxx"
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace selfupdate {

namespace {

inline uint32_t rotr(uint32_t x, uint32_t n)
{
    return (x >> n) | (x << (32 - n));
}

inline uint32_t choose(uint32_t x, uint32_t y, uint32_t z)
{
    return (x & y) ^ (~x & z);
}

inline uint32_t majority(uint32_t x, uint32_t y, uint32_t z)
{
    return (x & y) ^ (x & z) ^ (y & z);
}

inline uint32_t bigSigma0(uint32_t x)
{
    return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22);
}

inline uint32_t bigSigma1(uint32_t x)
{
    return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25);
}

inline uint32_t smallSigma0(uint32_t x)
{
    return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3);
}

inline uint32_t smallSigma1(uint32_t x)
{
    return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10);
}

const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

} // namespace

Sha256::Sha256()
    : _bitCount(0)
    , _bufferLen(0)
    , _finalized(false)
{
    reset();
}

void Sha256::reset()
{
    _state[0] = 0x6a09e667;
    _state[1] = 0xbb67ae85;
    _state[2] = 0x3c6ef372;
    _state[3] = 0xa54ff53a;
    _state[4] = 0x510e527f;
    _state[5] = 0x9b05688c;
    _state[6] = 0x1f83d9ab;
    _state[7] = 0x5be0cd19;

    _bitCount = 0;
    _bufferLen = 0;
    _finalized = false;
    _hexResult.clear();
    std::memset(_buffer, 0, sizeof(_buffer));
}

void Sha256::transform(const uint8_t block[64])
{
    uint32_t w[64];
    for (size_t i = 0; i < 16; ++i) {
        w[i] = (static_cast<uint32_t>(block[i * 4 + 0]) << 24) |
               (static_cast<uint32_t>(block[i * 4 + 1]) << 16) |
               (static_cast<uint32_t>(block[i * 4 + 2]) << 8) |
               (static_cast<uint32_t>(block[i * 4 + 3]));
    }
    for (size_t i = 16; i < 64; ++i) {
        w[i] = smallSigma1(w[i - 2]) + w[i - 7] + smallSigma0(w[i - 15]) + w[i - 16];
    }

    uint32_t a = _state[0];
    uint32_t b = _state[1];
    uint32_t c = _state[2];
    uint32_t d = _state[3];
    uint32_t e = _state[4];
    uint32_t f = _state[5];
    uint32_t g = _state[6];
    uint32_t h = _state[7];

    for (size_t i = 0; i < 64; ++i) {
        uint32_t t1 = h + bigSigma1(e) + choose(e, f, g) + K[i] + w[i];
        uint32_t t2 = bigSigma0(a) + majority(a, b, c);
        h = g;
        g = f;
        f = e;
        e = d + t1;
        d = c;
        c = b;
        b = a;
        a = t1 + t2;
    }

    _state[0] += a;
    _state[1] += b;
    _state[2] += c;
    _state[3] += d;
    _state[4] += e;
    _state[5] += f;
    _state[6] += g;
    _state[7] += h;
}

void Sha256::update(const void* data, size_t len)
{
    if (_finalized) {
        reset();
    }
    if (len == 0 || data == nullptr) {
        return;
    }

    const uint8_t* ptr = reinterpret_cast<const uint8_t*>(data);
    _bitCount += static_cast<uint64_t>(len) * 8;

    if (_bufferLen > 0) {
        size_t needed = 64 - _bufferLen;
        if (len < needed) {
            std::memcpy(_buffer + _bufferLen, ptr, len);
            _bufferLen += len;
            return;
        }
        std::memcpy(_buffer + _bufferLen, ptr, needed);
        transform(_buffer);
        ptr += needed;
        len -= needed;
        _bufferLen = 0;
    }

    while (len >= 64) {
        transform(ptr);
        ptr += 64;
        len -= 64;
    }

    if (len > 0) {
        std::memcpy(_buffer, ptr, len);
        _bufferLen = len;
    }
}

std::vector<uint8_t> Sha256::finalBytes()
{
    if (!_finalized) {
        _buffer[_bufferLen++] = 0x80;
        if (_bufferLen > 56) {
            std::memset(_buffer + _bufferLen, 0, 64 - _bufferLen);
            transform(_buffer);
            _bufferLen = 0;
        }
        std::memset(_buffer + _bufferLen, 0, 56 - _bufferLen);

        for (int i = 7; i >= 0; --i) {
            _buffer[56 + (7 - i)] = static_cast<uint8_t>((_bitCount >> (i * 8)) & 0xff);
        }
        transform(_buffer);
        _finalized = true;

        std::ostringstream ss;
        ss << std::hex << std::setfill('0');
        for (size_t i = 0; i < 8; ++i) {
            ss << std::setw(8) << _state[i];
        }
        _hexResult = ss.str();
    }

    std::vector<uint8_t> out(32);
    for (size_t i = 0; i < 8; ++i) {
        out[i * 4 + 0] = static_cast<uint8_t>((_state[i] >> 24) & 0xff);
        out[i * 4 + 1] = static_cast<uint8_t>((_state[i] >> 16) & 0xff);
        out[i * 4 + 2] = static_cast<uint8_t>((_state[i] >> 8) & 0xff);
        out[i * 4 + 3] = static_cast<uint8_t>(_state[i] & 0xff);
    }
    return out;
}

std::string Sha256::finalHex()
{
    if (!_finalized) {
        finalBytes();
    }
    return _hexResult;
}

std::string Sha256::hashBytes(const void* data, size_t len)
{
    Sha256 hasher;
    hasher.update(data, len);
    return hasher.finalHex();
}

std::string Sha256::hashString(const std::string& str)
{
    return hashBytes(str.data(), str.size());
}

std::string Sha256::hashFile(const std::string& path)
{
    std::ifstream stream(path, std::ios::binary);
    if (!stream.is_open()) {
        throw std::runtime_error("Cannot open file for SHA-256 calculation: " + path);
    }

    Sha256 hasher;
    char buffer[65536];
    while (stream.good()) {
        stream.read(buffer, sizeof(buffer));
        std::streamsize bytes = stream.gcount();
        if (bytes > 0) {
            hasher.update(buffer, static_cast<size_t>(bytes));
        }
    }
    return hasher.finalHex();
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
