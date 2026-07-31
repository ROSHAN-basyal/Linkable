import com.google.protobuf.gradle.proto

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.protobuf")
}

val releaseKeystore = providers.environmentVariable("LINKABLE_ANDROID_KEYSTORE").orNull
val releaseKeyAlias = providers.environmentVariable("LINKABLE_ANDROID_KEY_ALIAS").orNull
val releaseStorePassword = providers.environmentVariable("LINKABLE_ANDROID_STORE_PASSWORD").orNull
val releaseKeyPassword = providers.environmentVariable("LINKABLE_ANDROID_KEY_PASSWORD").orNull
val releaseSigningValues = listOf(releaseKeystore, releaseKeyAlias, releaseStorePassword, releaseKeyPassword)

android {
    namespace = "com.linkable"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.linkable"
        minSdk = 26
        targetSdk = 34
        versionCode = 3
        versionName = "0.3.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    val releaseSigning = if (releaseSigningValues.all { !it.isNullOrBlank() }) {
        signingConfigs.create("linkableRelease") {
            storeFile = file(releaseKeystore!!)
            storePassword = releaseStorePassword
            keyAlias = releaseKeyAlias
            keyPassword = releaseKeyPassword
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
        }
    } else {
        null
    }

    buildTypes {
        release {
            isDebuggable = false
            isMinifyEnabled = false
            signingConfig = releaseSigning
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

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.15"
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    sourceSets {
        getByName("main") {
            proto {
                srcDir(file("${rootDir}/../protocol/schemas"))
            }
        }
    }
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:4.27.0"
    }
    generateProtoTasks {
        all().configureEach {
            builtins {
                create("java") {
                    option("lite")
                }
            }
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2025.04.01")

    implementation("androidx.core:core-ktx:1.16.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("com.google.android.material:material:1.12.0")
    implementation("com.google.protobuf:protobuf-javalite:4.27.0")

    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")

    testImplementation("junit:junit:4.13.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
