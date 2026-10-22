# selfupdate.cmake
#
# Consumer CMake integration file for Selfso C++ selfupdate library
# Copyright (C) 2026, Charles Chiou

cmake_minimum_required(VERSION 3.16)

set(SELFUPDATE_WINDOWS_DIR "${CMAKE_CURRENT_LIST_DIR}")
set(SELFUPDATE_WINDOWS_INCLUDE_DIR "${SELFUPDATE_WINDOWS_DIR}/include")

set(SELFUPDATE_WINDOWS_HEADERS
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/UpdateManifest.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/UpdateState.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/Sha256.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/HttpTransport.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/SelfUpdateChecker.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/PackageDownloader.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/UpdateInstaller.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/SelfUpdateController.hxx"
    "${SELFUPDATE_WINDOWS_INCLUDE_DIR}/selfupdate/QtSelfUpdateBridge.hxx"
)

set(SELFUPDATE_WINDOWS_SOURCES
    "${SELFUPDATE_WINDOWS_DIR}/src/UpdateManifest.cxx"
    "${SELFUPDATE_WINDOWS_DIR}/src/Sha256.cxx"
    "${SELFUPDATE_WINDOWS_DIR}/src/HttpTransport.cxx"
    "${SELFUPDATE_WINDOWS_DIR}/src/SelfUpdateChecker.cxx"
    "${SELFUPDATE_WINDOWS_DIR}/src/PackageDownloader.cxx"
    "${SELFUPDATE_WINDOWS_DIR}/src/UpdateInstaller.cxx"
    "${SELFUPDATE_WINDOWS_DIR}/src/SelfUpdateController.cxx"
)

if(WIN32)
    set(SELFUPDATE_WINDOWS_PLATFORM_LIBS
        winhttp
        version
        shell32
        ole32
        advapi32
        user32
    )
else()
    find_package(Threads REQUIRED)
    set(SELFUPDATE_WINDOWS_PLATFORM_LIBS
        Threads::Threads
    )
endif()

function(selfupdate_target_sources target_name)
    target_sources(${target_name} PRIVATE ${SELFUPDATE_WINDOWS_SOURCES})
    target_include_directories(${target_name} PUBLIC ${SELFUPDATE_WINDOWS_INCLUDE_DIR})
    target_link_libraries(${target_name} PRIVATE ${SELFUPDATE_WINDOWS_PLATFORM_LIBS})
endfunction()
