package com.genaijerry.mirror

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Request

/** The header the backend reads the app token from (design decision D10). */
private const val AUTHORIZATION = "Authorization"

/**
 * What every call to the backend has in common.
 *
 * The app makes two kinds of call — the list of languages, and one frame to
 * translate — and both are shaped the same way: a path under the one base URL
 * this build was given, carrying this build's app token when it has one. Both
 * rules are written here once, so a third call cannot get either of them
 * subtly wrong.
 */
internal fun backendUrl(baseUrl: String, path: String): HttpUrl =
    baseUrl.toHttpUrl().newBuilder().addPathSegments(path).build()

/**
 * This request signed with the app token this build carries, or left unsigned
 * when it carries none.
 *
 * A backend started with `APP_TOKEN` refuses an app-facing call without the
 * header (design decision D10); a backend without the switch ignores it. So
 * sending it whenever there is one to send costs nothing either way, and the
 * token itself is never logged and never shown.
 */
internal fun Request.Builder.signedWith(appToken: String): Request.Builder = apply {
    val token = appToken.trim()
    if (token.isNotEmpty()) header(AUTHORIZATION, "Bearer $token")
}
