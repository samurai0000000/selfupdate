# Copyright (C) 2026, Charles Chiou

JAVA_HOME ?= $(shell ls -d "$$HOME"/.jdks/jdk-* 2>/dev/null | tail -n 1)
ANDROID_HOME ?= $(HOME)/Android/Sdk

export JAVA_HOME
export ANDROID_HOME

.PHONY: all test publish-all clean distclean

all:
	@if [ -f android/build.gradle.kts ]; then \
		./gradlew :selfupdate:assembleDebug :selfupdate:assembleRelease; \
	else \
		echo "android/build.gradle.kts not yet present (deferred to Envelope 2); skipping Gradle assemble."; \
	fi

test:
	python3 -m unittest discover -s tests -p "test_*.py" -v
	@if [ -f android/build.gradle.kts ]; then \
		./gradlew :selfupdate:testDebugUnitTest; \
	fi

publish-all:
	python3 scripts/publish_android_apk.py --publish-all

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@if [ -f android/build.gradle.kts ]; then \
		./gradlew clean; \
	fi

distclean: clean
	rm -rf .gradle build android/build 2>/dev/null || true
