package com.genaijerry.mirror

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

/** How long the app waits for the list of languages before giving up. */
private const val TIMEOUT_SECONDS = 10L

/** The path the backend answers the list on, under the base URL. */
private const val LANGUAGES_PATH = "v1/languages"

/**
 * The list of languages, read from the backend.
 *
 * `GET /v1/languages` answers `{"sources": [...], "targets": [...]}`, each
 * entry a code and a name. The backend checks its own configuration over
 * before it serves it, so anything this cannot read means a backend that is
 * broken or unreachable: it throws, and the picker says the languages are
 * unavailable rather than offering half a list.
 *
 * Nothing is remembered between calls. The picker asks again every time it
 * opens, which is what makes a language an operator has just added show up.
 *
 * The request is signed like every other call to the backend — see
 * [signedWith], which holds that rule for all of them. What it costs to get
 * wrong here is a picker: a build whose token a backend started with
 * `APP_TOKEN` refuses gets 401, and then the picker is empty forever.
 */
class BackendLanguageCatalogue(
    baseUrl: String = BackendConfig.baseUrl,
    private val appToken: String = BackendConfig.appToken,
    private val calls: Call.Factory = languagesHttpClient(),
) : LanguageCatalogueSource {

    private val url = backendUrl(baseUrl, LANGUAGES_PATH)

    override suspend fun catalogue(): LanguageCatalogue = withContext(Dispatchers.IO) {
        calls.newCall(languagesRequest()).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("The backend answered $LANGUAGES_PATH with ${response.code}")
            }
            parseCatalogue(response.body.string())
        }
    }

    private fun languagesRequest(): Request =
        Request.Builder().url(url).get().signedWith(appToken).build()
}

private fun languagesHttpClient(): OkHttpClient =
    OkHttpClient.Builder()
        .connectTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .readTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .build()

/**
 * Read one answer from `GET /v1/languages`.
 *
 * A missing list means the backend offers none of that kind; a list that is
 * not a list, or an entry without a code and a name, means an answer this app
 * cannot trust, so it throws.
 */
internal fun parseCatalogue(body: String): LanguageCatalogue =
    try {
        val payload = JSONObject(body)
        LanguageCatalogue(
            sources = payload.languageList("sources"),
            targets = payload.languageList("targets"),
        )
    } catch (failure: JSONException) {
        throw IOException("The backend's list of languages could not be read", failure)
    }

private fun JSONObject.languageList(name: String): List<LanguageOption> {
    if (!has(name) || isNull(name)) return emptyList()
    val entries: JSONArray = getJSONArray(name)
    return (0 until entries.length()).map { index ->
        val entry = entries.getJSONObject(index)
        LanguageOption(code = entry.text("code"), name = entry.text("name"))
    }
}

private fun JSONObject.text(field: String): String {
    val value = getString(field).trim()
    if (value.isEmpty()) throw JSONException("$field is empty")
    return value
}
