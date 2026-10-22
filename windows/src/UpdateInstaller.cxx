/*
 * UpdateInstaller.cxx
 *
 * Copyright (C) 2026, Charles Chiou
 */

#include "selfupdate/UpdateInstaller.hxx"
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <system_error>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <process.h>
#else
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

namespace selfupdate {

namespace {

#ifdef _WIN32

std::wstring utf8ToWide(const std::string& str)
{
    if (str.empty()) {
        return std::wstring();
    }
    int len = MultiByteToWideChar(CP_UTF8, 0, str.c_str(), static_cast<int>(str.size()), nullptr, 0);
    if (len <= 0) {
        return std::wstring();
    }
    std::wstring wstr(len, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, str.c_str(), static_cast<int>(str.size()), &wstr[0], len);
    return wstr;
}

std::string wideToUtf8(const std::wstring& wstr)
{
    if (wstr.empty()) {
        return std::string();
    }
    int len = WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.size()),
                                  nullptr, 0, nullptr, nullptr);
    if (len <= 0) {
        return std::string();
    }
    std::string str(len, '\0');
    WideCharToMultiByte(CP_UTF8, 0, wstr.c_str(), static_cast<int>(wstr.size()),
                        &str[0], len, nullptr, nullptr);
    return str;
}

uint32_t getCurrentProcessPid()
{
    return static_cast<uint32_t>(GetCurrentProcessId());
}

#else

uint32_t getCurrentProcessPid()
{
    return static_cast<uint32_t>(getpid());
}

#endif

std::string quoteArg(const std::string& arg)
{
    if (arg.empty()) {
        return "\"\"";
    }
    if (arg.find_first_of(" \t\n\v\"") == std::string::npos) {
        return arg;
    }
    std::string res = "\"";
    for (char c : arg) {
        if (c == '"') {
            res += "\\\"";
        } else {
            res += c;
        }
    }
    res += '"';
    return res;
}

std::string formatCommand(const std::string& exe, const std::vector<std::string>& args)
{
    std::string cmd = quoteArg(exe);
    for (const auto& a : args) {
        cmd += " ";
        cmd += quoteArg(a);
    }
    return cmd;
}

std::string formatTrampolineCommand(const std::string& scriptPath)
{
#ifdef _WIN32
    return "cmd.exe /c \"" + scriptPath + "\"";
#else
    return "sh \"" + scriptPath + "\"";
#endif
}

bool spawnDetachedProcess(const std::string& exePath, const std::vector<std::string>& args)
{
#ifdef _WIN32
    std::wstring cmdLine = utf8ToWide(formatCommand(exePath, args));
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    BOOL ok = CreateProcessW(nullptr, &cmdLine[0], nullptr, nullptr, FALSE,
                             CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
    if (ok) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return true;
    }
    return false;
#else
    pid_t pid = fork();
    if (pid < 0) {
        return false;
    }
    if (pid == 0) {
        setsid();
        std::vector<const char*> argv;
        argv.push_back(exePath.c_str());
        for (const auto& a : args) {
            argv.push_back(a.c_str());
        }
        argv.push_back(nullptr);
        execv(exePath.c_str(), const_cast<char* const*>(argv.data()));
        _exit(127);
    }
    return true;
#endif
}

bool launchTrampoline(const std::string& scriptPath)
{
#ifdef _WIN32
    std::wstring cmdLine = L"cmd.exe /c \"" + utf8ToWide(scriptPath) + L"\"";
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    BOOL ok = CreateProcessW(nullptr, &cmdLine[0], nullptr, nullptr, FALSE,
                             CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
    if (ok) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return true;
    }
    return false;
#else
    pid_t pid = fork();
    if (pid < 0) {
        return false;
    }
    if (pid == 0) {
        setsid();
        execl("/bin/sh", "sh", scriptPath.c_str(), static_cast<char*>(nullptr));
        _exit(127);
    }
    return true;
#endif
}

std::string generateInstallerTrampolineScript(const std::string& stagedInstallerPath,
                                             const std::string& installerArgs,
                                             const std::string& relaunchExe,
                                             const std::vector<std::string>& relaunchArgs,
                                             bool relaunchAfterInstall)
{
    std::filesystem::path installerP(stagedInstallerPath);
    std::filesystem::path scriptDir = installerP.parent_path();
    if (scriptDir.empty()) {
        scriptDir = ".";
    }

    uint32_t pid = getCurrentProcessPid();

#ifdef _WIN32
    std::filesystem::path scriptPath = scriptDir / "selfupdate_trampoline.cmd";
    std::ofstream out(scriptPath.string(), std::ios::out | std::ios::trunc | std::ios::binary);
    if (!out.is_open()) {
        return "";
    }

    out << "@echo off\r\n";
    out << "setlocal\r\n";
    out << ":wait_loop\r\n";
    out << "tasklist /fi \"pid eq " << pid << "\" 2>nul | find \"" << pid << "\" >nul\r\n";
    out << "if \"%ERRORLEVEL%\"==\"0\" (\r\n";
    out << "    timeout /t 1 /nobreak >nul 2>&1\r\n";
    out << "    goto wait_loop\r\n";
    out << ")\r\n";
    out << "start \"\" /WAIT \"" << stagedInstallerPath << "\"";
    if (!installerArgs.empty()) {
        out << " " << installerArgs;
    }
    out << "\r\n";
    out << "if %ERRORLEVEL% EQU 0 (\r\n";
    if (relaunchAfterInstall && !relaunchExe.empty()) {
        out << "    start \"\" " << formatCommand(relaunchExe, relaunchArgs) << "\r\n";
    }
    out << ")\r\n";
    out << "del \"%~f0\"\r\n";
    out.close();
    return scriptPath.string();
#else
    std::filesystem::path scriptPath = scriptDir / "selfupdate_trampoline.sh";
    std::ofstream out(scriptPath.string(), std::ios::out | std::ios::trunc);
    if (!out.is_open()) {
        return "";
    }

    out << "#!/bin/sh\n";
    out << "PID=" << pid << "\n";
    out << "if [ \"$PID\" -gt 0 ] 2>/dev/null; then\n";
    out << "    while kill -0 \"$PID\" 2>/dev/null; do\n";
    out << "        sleep 0.1\n";
    out << "    done\n";
    out << "fi\n";
    out << "\"" << stagedInstallerPath << "\"";
    if (!installerArgs.empty()) {
        out << " " << installerArgs;
    }
    out << "\n";
    out << "STATUS=$?\n";
    out << "if [ $STATUS -eq 0 ]; then\n";
    if (relaunchAfterInstall && !relaunchExe.empty()) {
        out << "    " << formatCommand(relaunchExe, relaunchArgs) << " &\n";
    }
    out << "fi\n";
    out << "rm -f \"$0\"\n";
    out.close();

    std::error_code ec;
    std::filesystem::permissions(scriptPath,
                                 std::filesystem::perms::owner_all |
                                 std::filesystem::perms::group_read | std::filesystem::perms::group_exec |
                                 std::filesystem::perms::others_read | std::filesystem::perms::others_exec,
                                 std::filesystem::perm_options::replace, ec);
    return scriptPath.string();
#endif
}

std::string generateBinaryCopyTrampolineScript(const std::string& stagedBinaryPath,
                                              const std::string& targetExe,
                                              const std::vector<std::string>& relaunchArgs,
                                              bool relaunchAfterInstall)
{
    std::filesystem::path stagedP(stagedBinaryPath);
    std::filesystem::path scriptDir = stagedP.parent_path();
    if (scriptDir.empty()) {
        scriptDir = ".";
    }

    uint32_t pid = getCurrentProcessPid();

#ifdef _WIN32
    std::filesystem::path scriptPath = scriptDir / "selfupdate_copy_trampoline.cmd";
    std::ofstream out(scriptPath.string(), std::ios::out | std::ios::trunc | std::ios::binary);
    if (!out.is_open()) {
        return "";
    }

    out << "@echo off\r\n";
    out << "setlocal\r\n";
    out << ":wait_loop\r\n";
    out << "tasklist /fi \"pid eq " << pid << "\" 2>nul | find \"" << pid << "\" >nul\r\n";
    out << "if \"%ERRORLEVEL%\"==\"0\" (\r\n";
    out << "    timeout /t 1 /nobreak >nul 2>&1\r\n";
    out << "    goto wait_loop\r\n";
    out << ")\r\n";
    out << "copy /y \"" << stagedBinaryPath << "\" \"" << targetExe << "\" >nul\r\n";
    out << "if %ERRORLEVEL% EQU 0 (\r\n";
    if (relaunchAfterInstall && !targetExe.empty()) {
        out << "    start \"\" " << formatCommand(targetExe, relaunchArgs) << "\r\n";
    }
    out << ")\r\n";
    out << "del \"%~f0\"\r\n";
    out.close();
    return scriptPath.string();
#else
    std::filesystem::path scriptPath = scriptDir / "selfupdate_copy_trampoline.sh";
    std::ofstream out(scriptPath.string(), std::ios::out | std::ios::trunc);
    if (!out.is_open()) {
        return "";
    }

    out << "#!/bin/sh\n";
    out << "PID=" << pid << "\n";
    out << "if [ \"$PID\" -gt 0 ] 2>/dev/null; then\n";
    out << "    while kill -0 \"$PID\" 2>/dev/null; do\n";
    out << "        sleep 0.1\n";
    out << "    done\n";
    out << "fi\n";
    out << "cp -f \"" << stagedBinaryPath << "\" \"" << targetExe << "\"\n";
    out << "chmod 0755 \"" << targetExe << "\"\n";
    out << "STATUS=$?\n";
    out << "if [ $STATUS -eq 0 ]; then\n";
    if (relaunchAfterInstall && !targetExe.empty()) {
        out << "    " << formatCommand(targetExe, relaunchArgs) << " &\n";
    }
    out << "fi\n";
    out << "rm -f \"$0\"\n";
    out.close();

    std::error_code ec;
    std::filesystem::permissions(scriptPath,
                                 std::filesystem::perms::owner_all |
                                 std::filesystem::perms::group_read | std::filesystem::perms::group_exec |
                                 std::filesystem::perms::others_read | std::filesystem::perms::others_exec,
                                 std::filesystem::perm_options::replace, ec);
    return scriptPath.string();
#endif
}

} // namespace

UpdateInstaller::UpdateInstaller(const InstallOptions& options)
    : _options(options)
{
}

const InstallOptions& UpdateInstaller::options() const
{
    return _options;
}

std::string UpdateInstaller::detectCurrentExecutablePath()
{
#ifdef _WIN32
    std::vector<wchar_t> wbuf(MAX_PATH);
    DWORD len = GetModuleFileNameW(nullptr, wbuf.data(), static_cast<DWORD>(wbuf.size()));
    while (len == wbuf.size() && GetLastError() == ERROR_INSUFFICIENT_BUFFER) {
        wbuf.resize(wbuf.size() * 2);
        len = GetModuleFileNameW(nullptr, wbuf.data(), static_cast<DWORD>(wbuf.size()));
    }
    if (len > 0) {
        return wideToUtf8(std::wstring(wbuf.data(), len));
    }
    return "";
#else
    char buf[4096];
    ssize_t len = ::readlink("/proc/self/exe", buf, sizeof(buf) - 1);
    if (len > 0) {
        buf[len] = '\0';
        return std::string(buf);
    }
    return "";
#endif
}

bool UpdateInstaller::cleanupStaleBackup(const std::string& exePath)
{
    std::string path = exePath.empty() ? detectCurrentExecutablePath() : exePath;
    if (path.empty()) {
        return true;
    }

    std::string oldPath = path + ".old";
    std::error_code ec;
    if (!std::filesystem::exists(oldPath, ec)) {
        return true;
    }

#ifdef _WIN32
    std::wstring wOld = utf8ToWide(oldPath);
    DWORD attrs = GetFileAttributesW(wOld.c_str());
    if (attrs != INVALID_FILE_ATTRIBUTES && (attrs & FILE_ATTRIBUTE_READONLY)) {
        SetFileAttributesW(wOld.c_str(), attrs & ~FILE_ATTRIBUTE_READONLY);
    }
    return DeleteFileW(wOld.c_str()) != 0;
#else
    std::filesystem::permissions(oldPath,
                                 std::filesystem::perms::owner_write,
                                 std::filesystem::perm_options::add,
                                 ec);
    return std::filesystem::remove(oldPath, ec);
#endif
}

InstallResult UpdateInstaller::executeBinaryCopy(const std::string& stagedBinaryPath,
                                                 const std::string& targetExePath) const
{
    InstallResult result;

    std::error_code ec;
    if (!std::filesystem::exists(stagedBinaryPath, ec) ||
        !std::filesystem::is_regular_file(stagedBinaryPath, ec)) {
        result.success = false;
        result.errorMessage = "Staged binary path does not exist or is not a regular file: " + stagedBinaryPath;
        return result;
    }

    std::string targetExe = targetExePath;
    if (targetExe.empty()) {
        targetExe = _options.targetExePath;
    }
    if (targetExe.empty()) {
        targetExe = _options.currentExePath;
    }
    if (targetExe.empty()) {
        targetExe = detectCurrentExecutablePath();
    }
    if (targetExe.empty()) {
        result.success = false;
        result.errorMessage = "Cannot determine target executable path for binary copy";
        return result;
    }

    std::string backupExe = targetExe + ".old";
    bool targetExists = std::filesystem::exists(targetExe, ec);
    bool renamed = false;

    if (targetExists) {
#ifdef _WIN32
        std::wstring wTarget = utf8ToWide(targetExe);
        std::wstring wBackup = utf8ToWide(backupExe);
        DWORD bAttrs = GetFileAttributesW(wBackup.c_str());
        if (bAttrs != INVALID_FILE_ATTRIBUTES && (bAttrs & FILE_ATTRIBUTE_READONLY)) {
            SetFileAttributesW(wBackup.c_str(), bAttrs & ~FILE_ATTRIBUTE_READONLY);
        }
        if (MoveFileExW(wTarget.c_str(), wBackup.c_str(), MOVEFILE_REPLACE_EXISTING)) {
            renamed = true;
        }
#else
        std::filesystem::rename(targetExe, backupExe, ec);
        if (!ec) {
            renamed = true;
        }
#endif
        if (!renamed) {
            // In-place rename failed. Fall back to PID-wait trampoline
            std::string trampoline = generateBinaryCopyTrampolineScript(
                stagedBinaryPath, targetExe, _options.relaunchArgs, _options.relaunchAfterInstall);
            if (trampoline.empty()) {
                result.success = false;
                result.errorMessage = "Failed to rename running executable to .old and failed to generate trampoline";
                return result;
            }
            result.trampolineScriptPath = trampoline;
            result.launchedCommand = formatTrampolineCommand(trampoline);
            result.requiresAppExit = true;
            if (!_options.dryRun) {
                if (!launchTrampoline(trampoline)) {
                    result.success = false;
                    result.errorMessage = "Failed to launch binary copy trampoline script";
                    return result;
                }
            }
            result.success = true;
            return result;
        }
    }

    // Copy staged binary over target executable
    bool copyOk = false;
#ifdef _WIN32
    std::wstring wStaged = utf8ToWide(stagedBinaryPath);
    std::wstring wTarget = utf8ToWide(targetExe);
    copyOk = (CopyFileW(wStaged.c_str(), wTarget.c_str(), FALSE) != 0);
#else
    std::filesystem::copy_file(stagedBinaryPath, targetExe,
                               std::filesystem::copy_options::overwrite_existing, ec);
    copyOk = !ec;
    if (copyOk) {
        std::filesystem::permissions(targetExe,
                                     std::filesystem::perms::owner_all |
                                     std::filesystem::perms::group_read | std::filesystem::perms::group_exec |
                                     std::filesystem::perms::others_read | std::filesystem::perms::others_exec,
                                     std::filesystem::perm_options::replace, ec);
    }
#endif

    if (!copyOk) {
        // Rollback invariant: restore targetExe from .old backup so executable is not lost!
        if (renamed) {
#ifdef _WIN32
            std::wstring wTarget = utf8ToWide(targetExe);
            std::wstring wBackup = utf8ToWide(backupExe);
            MoveFileExW(wBackup.c_str(), wTarget.c_str(), MOVEFILE_REPLACE_EXISTING);
#else
            std::filesystem::rename(backupExe, targetExe, ec);
#endif
        }
        result.success = false;
        result.backupExePath = renamed ? backupExe : "";
        result.errorMessage = "Failed to copy staged binary to target executable; restored backup";
        return result;
    }

    result.success = true;
    if (renamed) {
        result.backupExePath = backupExe;
    }

    if (_options.relaunchAfterInstall) {
        result.requiresAppExit = true;
        result.launchedCommand = formatCommand(targetExe, _options.relaunchArgs);
        if (!_options.dryRun) {
            spawnDetachedProcess(targetExe, _options.relaunchArgs);
        }
    } else {
        result.requiresAppExit = false;
    }

    return result;
}

InstallResult UpdateInstaller::executeSetupInstaller(const UpdateManifest& manifest,
                                                     const std::string& stagedInstallerPath) const
{
    InstallResult result;

    std::error_code ec;
    if (!std::filesystem::exists(stagedInstallerPath, ec) ||
        !std::filesystem::is_regular_file(stagedInstallerPath, ec)) {
        result.success = false;
        result.errorMessage = "Staged installer path does not exist or is not a regular file: " + stagedInstallerPath;
        return result;
    }

    std::string installerArgs = _options.installerArgsOverride.empty() ?
        manifest.installerArgs : _options.installerArgsOverride;

    std::string relaunchExe = _options.targetExePath;
    if (relaunchExe.empty()) {
        relaunchExe = _options.currentExePath;
    }
    if (relaunchExe.empty()) {
        relaunchExe = detectCurrentExecutablePath();
    }

    if (_options.waitForAppExitBeforeInstaller) {
        std::string trampoline = generateInstallerTrampolineScript(
            stagedInstallerPath, installerArgs, relaunchExe,
            _options.relaunchArgs, _options.relaunchAfterInstall);

        if (trampoline.empty()) {
            result.success = false;
            result.errorMessage = "Failed to generate installer trampoline script";
            return result;
        }

        result.trampolineScriptPath = trampoline;
        result.launchedCommand = formatTrampolineCommand(trampoline);
        result.requiresAppExit = true;

        if (!_options.dryRun) {
            if (!launchTrampoline(trampoline)) {
                result.success = false;
                result.errorMessage = "Failed to launch installer trampoline script";
                return result;
            }
        }
        result.success = true;
    } else {
        std::vector<std::string> argsVec;
        if (!installerArgs.empty()) {
            argsVec.push_back(installerArgs);
        }
        result.launchedCommand = formatCommand(stagedInstallerPath, argsVec);
        result.requiresAppExit = true;

        if (!_options.dryRun) {
            if (!spawnDetachedProcess(stagedInstallerPath, argsVec)) {
                result.success = false;
                result.errorMessage = "Failed to launch setup installer directly";
                return result;
            }
        }
        result.success = true;
    }

    return result;
}

InstallResult UpdateInstaller::executeUpdate(const UpdateManifest& manifest,
                                             const std::string& stagedPackagePath) const
{
    if (manifest.installMode == InstallMode::BinaryCopy) {
        return executeBinaryCopy(stagedPackagePath);
    } else {
        return executeSetupInstaller(manifest, stagedPackagePath);
    }
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
