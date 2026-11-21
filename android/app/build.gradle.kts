import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// 签名材料不入库：优先读 android/local.properties，其次读环境变量。
// 两者都没有时，release 包不带签名（可自行用 apksigner 签名）。
val localProps = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

fun signingProp(key: String, env: String): String? =
    localProps.getProperty(key) ?: System.getenv(env)

val keystoreProp = signingProp("pkb.storeFile", "PKB_KEYSTORE")
val keystoreFile: File? = keystoreProp?.takeIf { it.isNotBlank() }?.let { raw ->
    val f = File(raw)
    if (f.isAbsolute) f else rootProject.file(raw)
}

android {
    namespace = "com.nanming.pkb"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.nanming.pkb"
        minSdk = 26
        targetSdk = 34
        versionCode = 8
        versionName = "1.0.7"
    }

    signingConfigs {
        if (keystoreFile != null && keystoreFile.exists()) {
            create("release") {
                storeFile = keystoreFile
                storePassword = signingProp("pkb.storePassword", "PKB_STORE_PASSWORD")
                keyAlias = signingProp("pkb.keyAlias", "PKB_KEY_ALIAS") ?: "pkb"
                keyPassword = signingProp("pkb.keyPassword", "PKB_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.camera:camera-core:1.3.4")
    implementation("androidx.camera:camera-camera2:1.3.4")
    implementation("androidx.camera:camera-lifecycle:1.3.4")
    implementation("androidx.camera:camera-view:1.3.4")
    implementation("com.google.zxing:core:3.5.3")
}
