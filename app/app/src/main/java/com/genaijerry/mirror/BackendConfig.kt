package com.genaijerry.mirror

/**
 * Where this build of the app sends its requests, and what it signs them with.
 *
 * Both values come from the build flavour (design decisions D5 and D10), so
 * the one place that names a backend or carries its token is
 * `app/build.gradle.kts` — no code anywhere else may hold either.
 */
object BackendConfig {
    /** Base URL of the backend, always with a trailing slash. */
    val baseUrl: String = BuildConfig.BACKEND_BASE_URL.let {
        if (it.endsWith("/")) it else "$it/"
    }

    /**
     * The app token this build carries, or empty when the backend asks for
     * none.
     *
     * The backend's `APP_TOKEN` switch is off by default and so is this
     * (D10). When it is on, every app-facing call must send
     * `Authorization: Bearer <token>` or the backend answers 401. It is never
     * logged and never shown.
     */
    val appToken: String = BuildConfig.BACKEND_APP_TOKEN.trim()

    /** Whether this build has a token to send. */
    val sendsAppToken: Boolean get() = appToken.isNotEmpty()
}
