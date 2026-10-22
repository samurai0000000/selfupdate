# CMakeLists.txt
#
# Standalone test & build harness for selfupdate Windows / cross-platform library
# Copyright (C) 2026, Charles Chiou

cmake_minimum_required(VERSION 3.16)
project(selfupdate_windows LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
    add_compile_options(/W4 /WX)
else()
    add_compile_options(-Wall -Wextra -Werror -pedantic)
endif()

option(SELFUPDATE_SANITIZE "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
if(SELFUPDATE_SANITIZE AND NOT WIN32)
    add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
    add_link_options(-fsanitize=address,undefined)
endif()

include("${CMAKE_CURRENT_SOURCE_DIR}/selfupdate.cmake")

add_library(selfupdate_windows_lib STATIC)
selfupdate_target_sources(selfupdate_windows_lib)
target_include_directories(selfupdate_windows_lib PUBLIC ${SELFUPDATE_WINDOWS_INCLUDE_DIR})

if(WIN32)
    add_executable(test_win32_cross_compile
        tests/TestWin32CrossCompile.cxx
    )
    selfupdate_target_sources(test_win32_cross_compile)
endif()

option(SELFUPDATE_BUILD_TESTS "Build CppUTest + RapidCheck test suites" ON)

if(SELFUPDATE_BUILD_TESTS AND NOT WIN32)
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(CPPUTEST REQUIRED cpputest)
    find_library(RAPIDCHECK_LIBRARY rapidcheck REQUIRED)
    find_package(Threads REQUIRED)

    # test_update_manifest
    add_executable(test_update_manifest
        tests/TestMain.cxx
        tests/TestUpdateManifest.cxx
    )
    target_include_directories(test_update_manifest PRIVATE
        ${CPPUTEST_INCLUDE_DIRS}
        ${SELFUPDATE_WINDOWS_INCLUDE_DIR}
    )
    target_link_directories(test_update_manifest PRIVATE
        ${CPPUTEST_LIBRARY_DIRS}
    )
    target_link_libraries(test_update_manifest PRIVATE
        selfupdate_windows_lib
        ${CPPUTEST_LIBRARIES}
        ${RAPIDCHECK_LIBRARY}
        Threads::Threads
    )

    # test_downloader_and_checker
    add_executable(test_downloader_and_checker
        tests/TestMain.cxx
        tests/TestDownloaderAndChecker.cxx
    )
    target_include_directories(test_downloader_and_checker PRIVATE
        ${CPPUTEST_INCLUDE_DIRS}
        ${SELFUPDATE_WINDOWS_INCLUDE_DIR}
    )
    target_link_directories(test_downloader_and_checker PRIVATE
        ${CPPUTEST_LIBRARY_DIRS}
    )
    target_link_libraries(test_downloader_and_checker PRIVATE
        selfupdate_windows_lib
        ${CPPUTEST_LIBRARIES}
        ${RAPIDCHECK_LIBRARY}
        Threads::Threads
    )

    # test_installer_and_controller
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/tests/TestInstallerAndController.cxx")
        add_executable(test_installer_and_controller
            tests/TestMain.cxx
            tests/TestInstallerAndController.cxx
        )
        target_include_directories(test_installer_and_controller PRIVATE
            ${CPPUTEST_INCLUDE_DIRS}
            ${SELFUPDATE_WINDOWS_INCLUDE_DIR}
        )
        target_link_directories(test_installer_and_controller PRIVATE
            ${CPPUTEST_LIBRARY_DIRS}
        )
        target_link_libraries(test_installer_and_controller PRIVATE
            selfupdate_windows_lib
            ${CPPUTEST_LIBRARIES}
            ${RAPIDCHECK_LIBRARY}
            Threads::Threads
        )

        find_package(Qt6 COMPONENTS Core QUIET)
        if(TARGET Qt6::Core)
            target_link_libraries(test_installer_and_controller PRIVATE Qt6::Core)
            target_compile_definitions(test_installer_and_controller PRIVATE SELFUPDATE_HAVE_QT=1)
        else()
            find_package(Qt5 COMPONENTS Core QUIET)
            if(TARGET Qt5::Core)
                target_link_libraries(test_installer_and_controller PRIVATE Qt5::Core)
                target_compile_definitions(test_installer_and_controller PRIVATE SELFUPDATE_HAVE_QT=1)
            endif()
        endif()
    endif()
endif()
