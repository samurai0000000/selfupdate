/*
 * Copyright (C) 2026, Charles Chiou
 */

import java.io.File

/**
 * Reusable Gradle script plugin for Selfso Android applications.
 *
 * Registers helper tasks to automate manifest generation and portal publication:
 *   - generateVersionJson: Invokes scripts/gen_version_json.py to emit a single-app version.json.
 *   - publishSelfsoApk: Invokes scripts/publish_android_apk.py to stage APK, catalog, and HTML pages.
 *
 * Usage in an Android application build.gradle.kts:
 *   apply(from = "${rootProject.projectDir}/../selfupdate/android/gradle/version-manifest.gradle.kts")
 *
 * Configurable Gradle properties:
 *   - selfupdate.dir: Explicit path to the selfupdate repository root.
 *   - selfupdate.apk: Path to the target APK (defaults to release output APK).
 *   - selfupdate.output: Path for generated version.json.
 *   - selfso.webRoot: Path to www static portal root (defaults to ~/work/www/selfso/html).
 */

val selfupdateDir: File = run {
    val prop = project.findProperty("selfupdate.dir")?.toString()
    if (!prop.isNullOrBlank()) return@run File(prop)

    val env = System.getenv("SELFUPDATE_DIR")
    if (!env.isNullOrBlank()) return@run File(env)

    // Check sibling directory in typical multi-repo layout
    val sibling = File(rootProject.projectDir.parentFile, "selfupdate")
    if (sibling.exists() && File(sibling, "scripts/gen_version_json.py").exists()) {
        return@run sibling
    }

    // Default to rootProject directory
    rootProject.projectDir
}

val genVersionJsonScript = File(selfupdateDir, "scripts/gen_version_json.py")
val publishApkScript = File(selfupdateDir, "scripts/publish_android_apk.py")

tasks.register<Exec>("generateVersionJson") {
    group = "publishing"
    description = "Generates single-app version.json metadata from the built APK."

    val targetApk = project.findProperty("selfupdate.apk")?.toString()
        ?: layout.buildDirectory.file("outputs/apk/release/${project.name}-release.apk").get().asFile.absolutePath

    val targetOutput = project.findProperty("selfupdate.output")?.toString()
        ?: layout.buildDirectory.file("outputs/selfupdate/version.json").get().asFile.absolutePath

    doFirst {
        File(targetOutput).parentFile?.mkdirs()
    }

    commandLine(
        "python3",
        genVersionJsonScript.absolutePath,
        "--apk", targetApk,
        "--output", targetOutput
    )
}

tasks.register<Exec>("publishSelfsoApk") {
    group = "publishing"
    description = "Publishes the built APK to the Selfso static web portal and updates catalogs."

    val targetApk = project.findProperty("selfupdate.apk")?.toString()
        ?: layout.buildDirectory.file("outputs/apk/release/${project.name}-release.apk").get().asFile.absolutePath

    val webRoot = project.findProperty("selfso.webRoot")?.toString()
        ?: System.getenv("SELFSO_WEB_ROOT")

    val argsList = mutableListOf(
        "python3",
        publishApkScript.absolutePath,
        "--apk", targetApk
    )

    if (!webRoot.isNullOrBlank()) {
        argsList.add("--web-root")
        argsList.add(webRoot)
    }

    commandLine(argsList)
}
