import java.net.URI

plugins {
    // Kotlin support is built into the Android plugin from AGP 9; there is no
    // separate kotlin-android plugin to apply.
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// The systemTest flavour points at whichever backend the system test
// environment runs; the default is the local one (see gradle.properties).
val systemTestBackendUrl: String =
    (project.findProperty("mirror.systemTestBackendUrl") as String?) ?: "http://127.0.0.1:8000/"

// The app token the backend may ask for (design decision D10). Empty is the
// default and means the switch is off, which matches a backend with no
// APP_TOKEN set. A token inside an installed app is a deterrent, not a
// secret — it is a deployment fact, like the backend URL beside it, so it
// belongs to the build and never to the source.
fun appToken(property: String): String =
    (project.findProperty(property) as String?).orEmpty().trim()

val devAppToken: String = appToken("mirror.devAppToken")
val systemTestAppToken: String = appToken("mirror.systemTestAppToken")

// The staging flavour (epic 61, design decisions D6 and D7). The "Staging app"
// workflow passes these in as ORG_GRADLE_PROJECT_<name> environment variables,
// never on a command line and never from a committed file. The names hold no
// dot, because a dotted environment variable does not survive app/gradlew's
// /bin/sh. Unset, the address falls back to the developer one and the token to
// empty, so `assembleDebug` and `lint` still build every flavour with nothing
// set.
val stagingBackendUrl: String =
    (project.findProperty("mirrorStagingBackendUrl") as String?)?.trim()
        ?.takeIf { it.isNotEmpty() } ?: "http://10.0.2.2:8000/"
val stagingAppToken: String = appToken("mirrorStagingAppToken")

// The value is never printed: a failure names the property only.
run {
    val uri = runCatching { URI(stagingBackendUrl) }.getOrNull()
    if (uri == null || uri.scheme !in setOf("http", "https") || uri.host.isNullOrEmpty()) {
        throw GradleException("mirrorStagingBackendUrl is not an http or https URL")
    }
}

// Rises with every workflow run (design decision D9), so each staging build
// installs over the one before it.
val stagingVersionCode: Int =
    (project.findProperty("mirrorStagingVersionCode") as String?)?.trim()?.toIntOrNull() ?: 1

// One fixed test key signs every staging release build (design decision D8).
// The workflow writes the keystore to a private temporary file for the build
// only; without all four values the staging release build stays unsigned.
val stagingSigning: List<String> = listOf(
    "mirrorStagingKeystoreFile",
    "mirrorStagingStorePassword",
    "mirrorStagingKeyAlias",
    "mirrorStagingKeyPassword",
).map { (project.findProperty(it) as String?).orEmpty() }

android {
    namespace = "com.genaijerry.mirror"
    compileSdk = 37
    compileSdkMinor = 2

    defaultConfig {
        applicationId = "com.genaijerry.mirror"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (stagingSigning.all { it.isNotEmpty() } && file(stagingSigning[0]).isFile) {
            create("staging") {
                storeFile = file(stagingSigning[0])
                storePassword = stagingSigning[1]
                keyAlias = stagingSigning[2]
                keyPassword = stagingSigning[3]
                storeType = "pkcs12"
            }
        }
    }

    // One flavour per environment the app talks to (design decision D5: every
    // call goes to one backend, named here and nowhere else in the code).
    flavorDimensions += "environment"
    productFlavors {
        create("dev") {
            dimension = "environment"
            // 10.0.2.2 is the host machine as seen from the Android emulator.
            buildConfigField("String", "BACKEND_BASE_URL", "\"http://10.0.2.2:8000/\"")
            buildConfigField("String", "BACKEND_APP_TOKEN", "\"$devAppToken\"")
        }
        create("systemTest") {
            dimension = "environment"
            applicationIdSuffix = ".systemtest"
            versionNameSuffix = "-systemtest"
            buildConfigField("String", "BACKEND_BASE_URL", "\"$systemTestBackendUrl\"")
            buildConfigField("String", "BACKEND_APP_TOKEN", "\"$systemTestAppToken\"")
        }
        // The installable build testers get from a GitHub pre-release (epic
        // 61, design decision D5). Its own app id lets it sit beside a
        // developer build on one phone.
        create("staging") {
            dimension = "environment"
            applicationIdSuffix = ".staging"
            versionCode = stagingVersionCode
            // In full, not a suffix, so it matches the workflow's version name.
            versionName = "0.1.0-staging.$stagingVersionCode"
            buildConfigField("String", "BACKEND_BASE_URL", "\"$stagingBackendUrl\"")
            buildConfigField("String", "BACKEND_APP_TOKEN", "\"$stagingAppToken\"")
        }
    }
    // The debug build type sets its own debug key, which wins over a
    // flavour's, so only stagingRelease is signed with the test key.
    productFlavors.getByName("staging").signingConfig = signingConfigs.findByName("staging")

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    testOptions {
        unitTests {
            // Robolectric reads the merged resources and manifest from here.
            isIncludeAndroidResources = true

            all {
                // Robolectric reaches into the JDK's own file-descriptor
                // internals to stand in for Android's shared memory. A JDK of
                // 17 or later hides those unless the test JVM is told to open
                // them.
                it.jvmArgs("--add-opens=java.base/jdk.internal.access=ALL-UNNAMED")
            }
        }
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.activity.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)

    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)

    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.mlkit.text.recognition)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.okhttp)

    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation(libs.androidx.ui.test.junit4)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.kotlinx.coroutines.test)
}

// Kotlin comes from AGP 9's built-in support; this is where its compiler is
// configured. The JVM target matches compileOptions above.
kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}
