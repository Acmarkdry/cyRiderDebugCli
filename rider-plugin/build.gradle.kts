plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.25"
    id("org.jetbrains.intellij") version "1.17.4"
}

group = "com.cyriderdebug"
version = "0.1.0"

repositories {
    mavenCentral()
}

intellij {
    version.set("2024.1")
    type.set("RD")
}

tasks {
    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions.jvmTarget = "17"
    }
    patchPluginXml {
        sinceBuild.set("241")
        untilBuild.set("253.*")
    }
    buildSearchableOptions { enabled = false }
}
