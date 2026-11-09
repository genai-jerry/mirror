package com.genaijerry.mirror

import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONException
import org.json.JSONObject

/**
 * How long a cycle waits for the backend before giving up on it.
 *
 * The backend has to recognize the text and translate it inside this, so it is
 * generous — but it is bounded, because a cycle that never ends is a cycle
 * that never starts the next one.
 */
private const val TIMEOUT_SECONDS = 20L

/** The path the backend translates one frame on, under the base URL. */
private const val FRAMES_PATH = "v1/frames/translate"

private const val IMAGE_FIELD = "image"
private const val SOURCE_FIELD = "source_language"
private const val TARGET_FIELD = "target_language"

/** What the crop is called in the form. The backend names its own anyway. */
private const val IMAGE_FILENAME = "frame.jpg"

private val JPEG = "image/jpeg".toMediaType()

/**
 * Sends one cropped frame to the backend and reads back the translation.
 *
 * `POST /v1/frames/translate` takes a multipart form — the crop as a file, the
 * two language codes as fields — and answers with the recognized text, its
 * translation and a region hint (the design's API contract). The app never
 * calls Sarvam itself: the key lives in the backend and nowhere else (design
 * decision D5).
 *
 * Anything that is not a 200 throws, including the backend's own refusals — a
 * language it does not offer, the shared recognition allowance spent, Sarvam
 * slow or broken. The refresh cycle treats a throw as a finished-and-failed
 * cycle, and the overlay keeps its last good translation through it, which is
 * what the person sees instead of an error.
 *
 * @param languages read at the moment of each call, not at construction, so a
 *   pair chosen in the picker is used by the very next cycle.
 */
class BackendFrameTranslator(
    private val languages: () -> LanguagePair,
    baseUrl: String = BackendConfig.baseUrl,
    private val appToken: String = BackendConfig.appToken,
    private val calls: Call.Factory = framesHttpClient(),
) : FrameTranslator {

    private val url = backendUrl(baseUrl, FRAMES_PATH)

    override suspend fun translate(crop: FrameCrop): FrameTranslation =
        withContext(Dispatchers.IO) {
            calls.newCall(frameRequest(crop, languages())).execute().use { response ->
                if (!response.isSuccessful) {
                    throw IOException("The backend answered $FRAMES_PATH with ${response.code}")
                }
                parseFrameTranslation(response.body.string())
            }
        }

    private fun frameRequest(crop: FrameCrop, pair: LanguagePair): Request =
        Request.Builder()
            .url(url)
            .post(
                MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(IMAGE_FIELD, IMAGE_FILENAME, crop.jpeg.toRequestBody(JPEG))
                    .addFormDataPart(SOURCE_FIELD, pair.source)
                    .addFormDataPart(TARGET_FIELD, pair.target)
                    .build(),
            )
            .signedWith(appToken)
            .build()
}

/**
 * The client every frame goes out on: bounded, because a cycle that waits
 * forever is a cycle that never starts the next one. `internal` so a test can
 * read the bound it ships with.
 */
internal fun framesHttpClient(): OkHttpClient =
    OkHttpClient.Builder()
        .callTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .connectTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .writeTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .readTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
        .build()

/**
 * Read one answer from `POST /v1/frames/translate`.
 *
 * The two texts are always there — empty for a blank wall — so an answer
 * missing either of them is one this app cannot trust, and it throws rather
 * than reading the gap as a blank wall and wiping a good overlay off the
 * screen. A missing or null region hint is not a gap: it is the contract's way
 * of saying there was no text to point at.
 */
internal fun parseFrameTranslation(body: String): FrameTranslation =
    try {
        val payload = JSONObject(body)
        FrameTranslation(
            recognizedText = payload.getString("recognized_text"),
            translatedText = payload.getString("translated_text"),
            regionHint = payload.regionHint(),
            cached = payload.optBoolean("cached", false),
        )
    } catch (failure: JSONException) {
        throw IOException("The backend's translation of a frame could not be read", failure)
    }

private fun JSONObject.regionHint(): NormalizedRect? {
    if (!has("region_hint") || isNull("region_hint")) return null
    val hint = getJSONObject("region_hint")
    return NormalizedRect(
        x = hint.fraction("x"),
        y = hint.fraction("y"),
        width = hint.fraction("width"),
        height = hint.fraction("height"),
    )
}

private fun JSONObject.fraction(field: String): Float = getDouble(field).toFloat()
