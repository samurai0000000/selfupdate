# Copyright (C) 2026, Charles Chiou

JAVA_HOME ?= $(shell ls -d "$$HOME"/.jdks/jdk-* 2>/dev/null | tail -n 1)
ANDROID_HOME ?= $(HOME)/Android/Sdk
CMAKE ?= $(shell if [ -x /usr/bin/cmake ]; then echo /usr/bin/cmake; else echo cmake; fi)

export JAVA_HOME
export ANDROID_HOME

SANITIZE ?= 0
ifneq (,$(findstring -fsanitize,$(CFLAGS) $(CXXFLAGS)))
SANITIZE := 1
endif

CPP_BUILD_DIR := build/windows-cpp
ifeq ($(SANITIZE),1)
CPP_BUILD_DIR := build/windows-cpp-asan
endif

.PHONY: all test test-python test-android test-windows-cpp test-windows-mingw publish-all publish-android publish-windows clean distclean

all:
	@if [ -f android/build.gradle.kts ]; then \
		./gradlew :selfupdate:assembleDebug :selfupdate:assembleRelease; \
	else \
		echo "android/build.gradle.kts not yet present; skipping Gradle assemble."; \
	fi
	@if [ -f windows/CMakeLists.txt ]; then \
		mkdir -p $(CPP_BUILD_DIR); \
		if [ "$(SANITIZE)" = "1" ]; then \
			$(CMAKE) -B $(CPP_BUILD_DIR) -S windows -DSELFUPDATE_SANITIZE=ON; \
		else \
			$(CMAKE) -B $(CPP_BUILD_DIR) -S windows; \
		fi; \
		$(CMAKE) --build $(CPP_BUILD_DIR); \
	fi

test: test-python test-android test-windows-cpp test-windows-mingw

test-python:
	python3 -m unittest discover -s tests -p "test_*.py" -v

test-android:
	@if [ -f android/build.gradle.kts ]; then \
		./gradlew :selfupdate:testDebugUnitTest; \
	fi

test-windows-cpp:
	@mkdir -p $(CPP_BUILD_DIR)
	@if [ "$(SANITIZE)" = "1" ]; then \
		$(CMAKE) -B $(CPP_BUILD_DIR) -S windows -DSELFUPDATE_SANITIZE=ON; \
	else \
		$(CMAKE) -B $(CPP_BUILD_DIR) -S windows; \
	fi
	@$(CMAKE) --build $(CPP_BUILD_DIR)
	@$(CPP_BUILD_DIR)/test_update_manifest
	@$(CPP_BUILD_DIR)/test_downloader_and_checker
	@$(CPP_BUILD_DIR)/test_installer_and_controller

test-windows-mingw:
	@if which x86_64-w64-mingw32-g++-posix >/dev/null 2>&1; then \
		mkdir -p build/windows-mingw; \
		$(CMAKE) -B build/windows-mingw -S windows -DCMAKE_SYSTEM_NAME=Windows -DCMAKE_CXX_COMPILER=x86_64-w64-mingw32-g++-posix; \
		$(CMAKE) --build build/windows-mingw; \
		test -f build/windows-mingw/test_win32_cross_compile.exe; \
		x86_64-w64-mingw32-objdump -p build/windows-mingw/test_win32_cross_compile.exe | grep -i "DLL Name"; \
	fi

publish-all: publish-android publish-windows

publish-android:
	python3 scripts/publish_android_apk.py --publish-all

publish-windows:
	python3 scripts/publish_windows_app.py --publish-all

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@if [ -f android/build.gradle.kts ]; then \
		./gradlew clean; \
	fi
	rm -rf build 2>/dev/null || true

distclean: clean
	rm -rf .gradle android/build 2>/dev/null || true
