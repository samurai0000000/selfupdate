/*
 * Copyright (C) 2026, Charles Chiou
 */

import java.net.URI
import java.nio.file.FileSystems
import java.nio.file.Files
import java.util.jar.JarEntry
import java.util.jar.JarOutputStream

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val generateJdkHttpServerJar by tasks.registering {
    val outputFile = layout.buildDirectory.file("intermediates/jdk-httpserver.jar")
    outputs.file(outputFile)
    doLast {
        val targetJar = outputFile.get().asFile
        targetJar.parentFile.mkdirs()
        try {
            val fs = FileSystems.getFileSystem(URI.create("jrt:/"))
            val modPath = fs.getPath("/modules/jdk.httpserver")
            JarOutputStream(targetJar.outputStream()).use { jarOut ->
                Files.walk(modPath).use { stream ->
                    stream.forEach { path ->
                        if (Files.isRegularFile(path)) {
                            val rel = modPath.relativize(path).toString()
                            jarOut.putNextEntry(JarEntry(rel))
                            Files.copy(path, jarOut)
                            jarOut.closeEntry()
                        }
                    }
                }
            }
        } catch (_: Exception) {
            // Ignored if jrt:/ is unavailable
        }
    }
}

android {
    namespace = "com.selfso.selfupdate"
    compileSdk = 35

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "consumer-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation(files(generateJdkHttpServerJar))
}
