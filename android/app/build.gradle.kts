plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.example.lottoinsight"
    compileSdk = 37
    defaultConfig {
        applicationId = "com.example.lottoinsight"
        minSdk = 26
        targetSdk = 37
        versionCode = 2
        versionName = "2.0.0"
        manifestPlaceholders["usesCleartextTraffic"] = "false"
        buildConfigField(
        "String",
        "PAGES_BASE_URL",
        "\"https://gongdu.github.io/lotto_insight\""
        )
    }
    buildTypes {
        getByName("debug") { manifestPlaceholders["usesCleartextTraffic"] = "true" }
        getByName("release") { manifestPlaceholders["usesCleartextTraffic"] = "false" }
    }
    buildFeatures { compose = true; buildConfig = true }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.08.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.work:work-runtime-ktx:2.11.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
}
