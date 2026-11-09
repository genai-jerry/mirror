package com.genaijerry.mirror

/**
 * Where this build of the app sends its requests.
 *
 * The value comes from the build flavour (design decision D5), so the one
 * place that names a backend is `app/build.gradle.kts` — no code anywhere
 * else may hold a URL.
 */
object BackendConfig {
    /** Base URL of the backend, always with a trailing slash. */
    val baseUrl: String = BuildConfig.BACKEND_BASE_URL.let {
        if (it.endsWith("/")) it else "$it/"
    }
}
