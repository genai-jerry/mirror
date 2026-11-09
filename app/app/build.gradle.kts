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

    // One flavour per environment the app talks to (design decision D5: every
    // call goes to one backend, named here and nowhere else in the code).
    flavorDimensions += "environment"
    productFlavors {
        create("dev") {
            dimension = "environment"
            // 10.0.2.2 is the host machine as seen from the Android emulator.
            buildConfigField("String", "BACKEND_BASE_URL", "\"http://10.0.2.2:8000/\"")
        }
        create("systemTest") {
            dimension = "environment"
            applicationIdSuffix = ".systemtest"
            versionNameSuffix = "-systemtest"
            buildConfigField("String", "BACKEND_BASE_URL", "\"$systemTestBackendUrl\"")
        }
    }

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

    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation(libs.androidx.ui.test.junit4)
}

// Kotlin comes from AGP 9's built-in support; this is where its compiler is
// configured. The JVM target matches compileOptions above.
kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}
