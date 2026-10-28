/*
 * UpdateManifest.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/UpdateManifest.hxx"
#include <algorithm>
#include <cctype>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace selfupdate {

namespace {

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

std::string toLower(const std::string& str)
{
    std::string out = str;
    for (char& c : out) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return out;
}

// Minimal recursive-descent RFC 8259 JSON parser
enum class JsonType {
    Null,
    Bool,
    Number,
    String,
    Array,
    Object
};

struct JsonValue {
    JsonType type = JsonType::Null;
    bool boolVal = false;
    int64_t intVal = 0;
    double doubleVal = 0.0;
    std::string strVal;
    std::vector<JsonValue> arrVal;
    std::map<std::string, JsonValue> objVal;

    bool isObject() const { return type == JsonType::Object; }
    bool isArray() const { return type == JsonType::Array; }
    bool isString() const { return type == JsonType::String; }
    bool isNumber() const { return type == JsonType::Number; }

    const JsonValue* find(const std::string& key) const
    {
        if (type != JsonType::Object) {
            return nullptr;
        }
        auto it = objVal.find(key);
        if (it != objVal.end()) {
            return &it->second;
        }
        return nullptr;
    }

    std::string getString(const std::string& key, const std::string& def = "") const
    {
        const JsonValue* v = find(key);
        if (v && v->isString()) {
            return v->strVal;
        }
        return def;
    }

    int64_t getInt(const std::string& key, int64_t def = 0) const
    {
        const JsonValue* v = find(key);
        if (v && v->isNumber()) {
            return v->intVal;
        }
        return def;
    }
};

class JsonParser {
public:
    explicit JsonParser(const std::string& input)
        : _src(input)
        , _pos(0)
    {
    }

    JsonValue parse()
    {
        skipWhitespace();
        if (_pos >= _src.size()) {
            throw std::invalid_argument("Empty JSON input");
        }
        JsonValue val = parseValue();
        skipWhitespace();
        if (_pos < _src.size()) {
            throw std::invalid_argument("Unexpected trailing characters in JSON");
        }
        return val;
    }

private:
    void skipWhitespace()
    {
        while (_pos < _src.size()) {
            char c = _src[_pos];
            if (c == ' ' || c == '\t' || c == '\r' || c == '\n') {
                _pos++;
            } else {
                break;
            }
        }
    }

    char peek()
    {
        return (_pos < _src.size()) ? _src[_pos] : '\0';
    }

    char get()
    {
        return (_pos < _src.size()) ? _src[_pos++] : '\0';
    }

    JsonValue parseValue()
    {
        skipWhitespace();
        char c = peek();
        if (c == '{') {
            return parseObject();
        }
        if (c == '[') {
            return parseArray();
        }
        if (c == '"') {
            return parseString();
        }
        if (c == 't' || c == 'f') {
            return parseBool();
        }
        if (c == 'n') {
            return parseNull();
        }
        if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) {
            return parseNumber();
        }
        throw std::invalid_argument("Unexpected token parsing JSON at position " + std::to_string(_pos));
    }

    JsonValue parseObject()
    {
        get(); // consume '{'
        JsonValue val;
        val.type = JsonType::Object;
        skipWhitespace();
        if (peek() == '}') {
            get();
            return val;
        }

        while (_pos < _src.size()) {
            skipWhitespace();
            if (peek() != '"') {
                throw std::invalid_argument("Expected string key in object at position " + std::to_string(_pos));
            }
            JsonValue keyVal = parseString();
            std::string key = keyVal.strVal;

            skipWhitespace();
            if (get() != ':') {
                throw std::invalid_argument("Expected ':' after key in object at position " + std::to_string(_pos));
            }

            JsonValue memberVal = parseValue();
            val.objVal[key] = memberVal;

            skipWhitespace();
            char nextChar = get();
            if (nextChar == '}') {
                return val;
            }
            if (nextChar != ',') {
                throw std::invalid_argument("Expected ',' or '}' in object at position " + std::to_string(_pos));
            }
        }
        throw std::invalid_argument("Unterminated object in JSON");
    }

    JsonValue parseArray()
    {
        get(); // consume '['
        JsonValue val;
        val.type = JsonType::Array;
        skipWhitespace();
        if (peek() == ']') {
            get();
            return val;
        }

        while (_pos < _src.size()) {
            val.arrVal.push_back(parseValue());
            skipWhitespace();
            char nextChar = get();
            if (nextChar == ']') {
                return val;
            }
            if (nextChar != ',') {
                throw std::invalid_argument("Expected ',' or ']' in array at position " + std::to_string(_pos));
            }
        }
        throw std::invalid_argument("Unterminated array in JSON");
    }

    JsonValue parseString()
    {
        get(); // consume '"'
        std::string s;
        while (_pos < _src.size()) {
            char c = get();
            if (c == '"') {
                JsonValue val;
                val.type = JsonType::String;
                val.strVal = s;
                return val;
            }
            if (c == '\\') {
                if (_pos >= _src.size()) {
                    throw std::invalid_argument("Unterminated escape sequence in string");
                }
                char esc = get();
                switch (esc) {
                case '"': s.push_back('"'); break;
                case '\\': s.push_back('\\'); break;
                case '/': s.push_back('/'); break;
                case 'b': s.push_back('\b'); break;
                case 'f': s.push_back('\f'); break;
                case 'n': s.push_back('\n'); break;
                case 'r': s.push_back('\r'); break;
                case 't': s.push_back('\t'); break;
                case 'u': {
                    if (_pos + 4 > _src.size()) {
                        throw std::invalid_argument("Truncated \\u unicode escape");
                    }
                    uint32_t codepoint = 0;
                    for (int i = 0; i < 4; ++i) {
                        char h = get();
                        codepoint <<= 4;
                        if (h >= '0' && h <= '9') codepoint |= (h - '0');
                        else if (h >= 'a' && h <= 'f') codepoint |= (h - 'a' + 10);
                        else if (h >= 'A' && h <= 'F') codepoint |= (h - 'A' + 10);
                        else throw std::invalid_argument("Invalid hex in \\u unicode escape");
                    }
                    // Simple UTF-8 encoding
                    if (codepoint <= 0x7f) {
                        s.push_back(static_cast<char>(codepoint));
                    } else if (codepoint <= 0x7ff) {
                        s.push_back(static_cast<char>(0xc0 | ((codepoint >> 6) & 0x1f)));
                        s.push_back(static_cast<char>(0x80 | (codepoint & 0x3f)));
                    } else {
                        s.push_back(static_cast<char>(0xe0 | ((codepoint >> 12) & 0x0f)));
                        s.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3f)));
                        s.push_back(static_cast<char>(0x80 | (codepoint & 0x3f)));
                    }
                    break;
                }
                default:
                    throw std::invalid_argument("Unknown escape character in string: \\" + std::string(1, esc));
                }
            } else {
                s.push_back(c);
            }
        }
        throw std::invalid_argument("Unterminated string in JSON");
    }

    JsonValue parseBool()
    {
        if (_src.compare(_pos, 4, "true") == 0) {
            _pos += 4;
            JsonValue val;
            val.type = JsonType::Bool;
            val.boolVal = true;
            return val;
        }
        if (_src.compare(_pos, 5, "false") == 0) {
            _pos += 5;
            JsonValue val;
            val.type = JsonType::Bool;
            val.boolVal = false;
            return val;
        }
        throw std::invalid_argument("Invalid boolean value in JSON");
    }

    JsonValue parseNull()
    {
        if (_src.compare(_pos, 4, "null") == 0) {
            _pos += 4;
            JsonValue val;
            val.type = JsonType::Null;
            return val;
        }
        throw std::invalid_argument("Invalid null literal in JSON");
    }

    JsonValue parseNumber()
    {
        size_t start = _pos;
        if (peek() == '-') {
            _pos++;
        }
        if (!std::isdigit(static_cast<unsigned char>(peek()))) {
            throw std::invalid_argument("Expected digit in number at position " + std::to_string(_pos));
        }
        while (std::isdigit(static_cast<unsigned char>(peek()))) {
            _pos++;
        }

        bool isFloating = false;
        if (peek() == '.') {
            isFloating = true;
            _pos++;
            if (!std::isdigit(static_cast<unsigned char>(peek()))) {
                throw std::invalid_argument("Expected digit after decimal point at position " + std::to_string(_pos));
            }
            while (std::isdigit(static_cast<unsigned char>(peek()))) {
                _pos++;
            }
        }

        if (peek() == 'e' || peek() == 'E') {
            isFloating = true;
            _pos++;
            if (peek() == '+' || peek() == '-') {
                _pos++;
            }
            if (!std::isdigit(static_cast<unsigned char>(peek()))) {
                throw std::invalid_argument("Expected digit in exponent at position " + std::to_string(_pos));
            }
            while (std::isdigit(static_cast<unsigned char>(peek()))) {
                _pos++;
            }
        }

        std::string numStr = _src.substr(start, _pos - start);
        JsonValue val;
        val.type = JsonType::Number;
        if (isFloating) {
            val.doubleVal = std::stod(numStr);
            val.intVal = static_cast<int64_t>(val.doubleVal);
        } else {
            val.intVal = std::stoll(numStr);
            val.doubleVal = static_cast<double>(val.intVal);
        }
        return val;
    }

    const std::string& _src;
    size_t _pos;
};

} // namespace

std::string UpdateManifest::normalizeManifestUrl(const std::string& url)
{
    std::string s = trim(url);
    if (s.empty()) {
        return std::string(DEFAULT_MANIFEST_URL) + "version.json";
    }
    if (s.back() == '/') {
        return s + "version.json";
    }
    return s;
}

std::string UpdateManifest::normalizeApplicationId(const std::string& appId)
{
    std::string s = trim(appId);
    const std::string debugSuffix = ".debug";
    if (s.size() > debugSuffix.size() &&
        s.compare(s.size() - debugSuffix.size(), debugSuffix.size(), debugSuffix) == 0) {
        return s.substr(0, s.size() - debugSuffix.size());
    }
    return s;
}

std::string UpdateManifest::resolveRelativeUrl(const std::string& baseUrl,
                                               const std::string& relativeOrAbsUrl)
{
    std::string rel = trim(relativeOrAbsUrl);
    if (rel.rfind("http://", 0) == 0 || rel.rfind("https://", 0) == 0) {
        return rel;
    }

    std::string normBase = normalizeManifestUrl(baseUrl);
    if (rel.rfind("/", 0) == 0) {
        auto schemeEnd = normBase.find("://");
        if (schemeEnd != std::string::npos) {
            auto hostEnd = normBase.find('/', schemeEnd + 3);
            std::string origin = (hostEnd != std::string::npos)
                                     ? normBase.substr(0, hostEnd)
                                     : normBase;
            return origin + rel;
        }
        return rel;
    }

    auto lastSlash = normBase.rfind('/');
    if (lastSlash != std::string::npos) {
        return normBase.substr(0, lastSlash + 1) + rel;
    }
    return normBase + "/" + rel;
}

int UpdateManifest::compareVersions(const std::string& lhs, const std::string& rhs)
{
    std::string l = trim(lhs);
    std::string r = trim(rhs);
    if (!l.empty() && (l[0] == 'v' || l[0] == 'V')) {
        l = l.substr(1);
    }
    if (!r.empty() && (r[0] == 'v' || r[0] == 'V')) {
        r = r.substr(1);
    }

    // Split primary from prerelease/build suffix
    std::string lPrerelease;
    std::string rPrerelease;
    auto lDash = l.find('-');
    if (lDash != std::string::npos) {
        lPrerelease = l.substr(lDash + 1);
        l = l.substr(0, lDash);
    }
    auto rDash = r.find('-');
    if (rDash != std::string::npos) {
        rPrerelease = r.substr(rDash + 1);
        r = r.substr(0, rDash);
    }

    auto parseComponents = [](const std::string& s) -> std::vector<int64_t> {
        std::vector<int64_t> parts;
        std::istringstream ss(s);
        std::string token;
        while (std::getline(ss, token, '.')) {
            if (token.empty()) {
                parts.push_back(0);
                continue;
            }
            int64_t num = 0;
            size_t idx = 0;
            while (idx < token.size() && std::isdigit(static_cast<unsigned char>(token[idx]))) {
                num = num * 10 + (token[idx] - '0');
                idx++;
            }
            parts.push_back(num);
        }
        return parts;
    };

    std::vector<int64_t> lParts = parseComponents(l);
    std::vector<int64_t> rParts = parseComponents(r);

    size_t maxParts = std::max(lParts.size(), rParts.size());
    lParts.resize(maxParts, 0);
    rParts.resize(maxParts, 0);

    for (size_t i = 0; i < maxParts; ++i) {
        if (lParts[i] > rParts[i]) {
            return 1;
        }
        if (lParts[i] < rParts[i]) {
            return -1;
        }
    }

    // If numeric parts are identical, release > prerelease
    if (lPrerelease.empty() && !rPrerelease.empty()) {
        return 1;
    }
    if (!lPrerelease.empty() && rPrerelease.empty()) {
        return -1;
    }
    if (lPrerelease > rPrerelease) {
        return 1;
    }
    if (lPrerelease < rPrerelease) {
        return -1;
    }

    return 0;
}

int64_t UpdateManifest::parseVersionCode(const std::string& versionName)
{
    std::string s = trim(versionName);
    if (!s.empty() && (s[0] == 'v' || s[0] == 'V')) {
        s = s.substr(1);
    }
    auto dash = s.find('-');
    if (dash != std::string::npos) {
        s = s.substr(0, dash);
    }

    int64_t major = 0;
    int64_t minor = 0;
    int64_t patch = 0;

    std::istringstream ss(s);
    std::string token;
    int index = 0;
    while (std::getline(ss, token, '.')) {
        int64_t val = 0;
        for (char c : token) {
            if (std::isdigit(static_cast<unsigned char>(c))) {
                val = val * 10 + (c - '0');
            } else {
                break;
            }
        }
        if (index == 0) major = val;
        else if (index == 1) minor = val;
        else if (index == 2) patch = val;
        index++;
    }

    return major * 10000 + minor * 100 + patch;
}

bool UpdateManifest::isNewerThan(const std::string& installedVersionName,
                                 int64_t installedVersionCode) const
{
    if (!installedVersionName.empty() && !versionName.empty()) {
        int cmp = compareVersions(versionName, installedVersionName);
        if (cmp > 0) {
            return true;
        }
        if (cmp < 0) {
            return false;
        }
        if (installedVersionCode > 0 && versionCode > installedVersionCode) {
            return true;
        }
        return false;
    }
    return versionCode > installedVersionCode;
}

UpdateManifest UpdateManifest::fromJson(const std::string& jsonString,
                                        const std::string& manifestUrl,
                                        const std::string& targetIdOrSlug)
{
    JsonParser parser(jsonString);
    JsonValue root = parser.parse();
    if (!root.isObject()) {
        throw std::invalid_argument("Manifest JSON root must be an object");
    }

    std::string effectiveBaseUrl = manifestUrl;
    if (root.find("baseUrl") && root.find("baseUrl")->isString()) {
        effectiveBaseUrl = root.getString("baseUrl");
    }

    const JsonValue* appNode = nullptr;
    const JsonValue* apps = root.find("apps");
    if (apps != nullptr) {
        if (!apps->isObject()) {
            throw std::invalid_argument("'apps' in catalog must be an object");
        }

        std::string target = trim(targetIdOrSlug);
        std::string normalizedTarget = normalizeApplicationId(target);

        if (!target.empty()) {
            // Direct key match
            appNode = apps->find(target);
            if (!appNode && !normalizedTarget.empty()) {
                appNode = apps->find(normalizedTarget);
            }
            if (!appNode) {
                // Search by inner slug or applicationId
                for (const auto& pair : apps->objVal) {
                    if (pair.second.isObject()) {
                        std::string s = pair.second.getString("slug");
                        std::string aid = pair.second.getString("applicationId");
                        if (s == target || aid == target || normalizeApplicationId(aid) == normalizedTarget) {
                            appNode = &pair.second;
                            break;
                        }
                    }
                }
            }
            if (!appNode) {
                throw std::invalid_argument("Application '" + target + "' not found in catalog");
            }
        } else {
            // targetIdOrSlug is empty: if apps has exactly 1 entry, use it
            if (apps->objVal.size() == 1) {
                appNode = &(apps->objVal.begin()->second);
            } else {
                throw std::invalid_argument("Catalog contains " + std::to_string(apps->objVal.size()) +
                                           " apps; targetIdOrSlug required for selection");
            }
        }
    } else {
        // Single-app root manifest
        appNode = &root;
    }

    if (!appNode->isObject()) {
        throw std::invalid_argument("Selected application node must be an object");
    }

    UpdateManifest m;
    m.applicationId = appNode->getString("applicationId");
    if (m.applicationId.empty()) {
        throw std::invalid_argument("Manifest missing or empty applicationId");
    }

    m.versionName = appNode->getString("versionName");
    if (m.versionName.empty()) {
        throw std::invalid_argument("Manifest missing or empty versionName");
    }

    m.versionCode = appNode->getInt("versionCode", 0);
    if (m.versionCode <= 0) {
        throw std::invalid_argument("Manifest versionCode must be greater than zero");
    }

    std::string rawPkg = appNode->getString("packageUrl");
    if (rawPkg.empty()) {
        rawPkg = appNode->getString("downloadUrl");
    }
    if (rawPkg.empty()) {
        rawPkg = appNode->getString("apkUrl");
    }
    if (rawPkg.empty()) {
        throw std::invalid_argument("Manifest missing packageUrl, downloadUrl, or apkUrl");
    }
    m.packageUrl = resolveRelativeUrl(effectiveBaseUrl, rawPkg);

    std::string rawSha = trim(appNode->getString("sha256"));
    if (rawSha.size() != 64) {
        throw std::invalid_argument("Manifest sha256 checksum must be exactly 64 hex characters");
    }
    for (char c : rawSha) {
        if (!std::isxdigit(static_cast<unsigned char>(c))) {
            throw std::invalid_argument("Manifest sha256 checksum contains non-hexadecimal character");
        }
    }
    m.sha256 = toLower(rawSha);

    m.sizeBytes = appNode->getInt("sizeBytes", -1);

    std::string modeStr = toLower(appNode->getString("installMode"));
    if (modeStr.empty()) {
        modeStr = toLower(appNode->getString("installType"));
    }
    if (modeStr == "binary" || modeStr == "binarycopy") {
        m.installMode = InstallMode::BinaryCopy;
    } else {
        m.installMode = InstallMode::Installer;
    }

    m.installerArgs = appNode->getString("installerArgs");
    m.executableName = appNode->getString("executableName");
    m.arch = appNode->getString("arch", "x86_64");
    if (m.arch.empty()) {
        m.arch = "x86_64";
    }
    m.minOs = appNode->getString("minOs", "Windows 10 (64-bit)+");
    if (m.minOs.empty()) {
        m.minOs = "Windows 10 (64-bit)+";
    }
    m.slug = appNode->getString("slug");
    m.title = appNode->getString("title");

    std::string rawPage = appNode->getString("pageUrl");
    if (!rawPage.empty()) {
        m.pageUrl = resolveRelativeUrl(effectiveBaseUrl, rawPage);
    }
    m.publishedAt = appNode->getString("publishedAt");
    m.releaseNotes = appNode->getString("releaseNotes");

    const JsonValue* latestNode = appNode->find("latest");
    if (latestNode && latestNode->isObject()) {
        std::string rawLatestPkg = latestNode->getString("packageUrl");
        if (rawLatestPkg.empty()) {
            rawLatestPkg = latestNode->getString("downloadUrl");
        }
        if (rawLatestPkg.empty()) {
            rawLatestPkg = latestNode->getString("apkUrl");
        }
        if (!rawLatestPkg.empty()) {
            m.latestPackageUrl = resolveRelativeUrl(effectiveBaseUrl, rawLatestPkg);
        }
        std::string rawLatestSha = trim(latestNode->getString("sha256"));
        if (rawLatestSha.size() == 64) {
            bool hexOk = true;
            for (char c : rawLatestSha) {
                if (!std::isxdigit(static_cast<unsigned char>(c))) {
                    hexOk = false;
                    break;
                }
            }
            if (hexOk) {
                m.latestSha256 = toLower(rawLatestSha);
            }
        }
        m.latestSizeBytes = latestNode->getInt("sizeBytes", 0);
        m.latestPublishedAt = latestNode->getString("publishedAt");
    }

    return m;
}

UpdateManifest UpdateManifest::reinstallManifest() const
{
    UpdateManifest copy = *this;
    if (!latestPackageUrl.empty() && !latestSha256.empty()) {
        copy.packageUrl = latestPackageUrl;
        copy.sha256 = latestSha256;
        if (latestSizeBytes > 0) {
            copy.sizeBytes = latestSizeBytes;
        }
        if (!latestPublishedAt.empty()) {
            copy.publishedAt = latestPublishedAt;
        }
    }
    return copy;
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
