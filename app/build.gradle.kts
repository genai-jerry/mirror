// Root of the Android half of the product (design decision D1). The app
// module is :app; the backend half lives in ../backend and is built by its
// own tools.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
}
