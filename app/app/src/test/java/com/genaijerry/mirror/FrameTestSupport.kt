package com.genaijerry.mirror

import java.io.IOException

/**
 * What the tests use instead of the backend's frame endpoint. No test sends a
 * frame to a real one, and no test reaches Sarvam.
 *
 * @param answer what the next cycle gets back.
 * @param failure set this and every cycle fails instead — a backend that is
 *   down, slow or out of recognition allowance all look like this to the app.
 */
class FakeFrameTranslator(
    var answer: FrameTranslation = aTranslationOf("കേരളം", "Kerala"),
    var failure: IOException? = null,
) : FrameTranslator {

    /** The crops the app has sent, newest last. */
    val sent = mutableListOf<FrameCrop>()

    override suspend fun translate(crop: FrameCrop): FrameTranslation {
        sent += crop
        failure?.let { throw it }
        return answer
    }
}

/**
 * One answer from the frame endpoint: [recognized] read as [translated], in
 * the middle of the crop it was sent.
 */
fun aTranslationOf(
    recognized: String,
    translated: String,
    regionHint: NormalizedRect? = MIDDLE_OF_THE_CROP,
    cached: Boolean = false,
) = FrameTranslation(
    recognizedText = recognized,
    translatedText = translated,
    regionHint = regionHint,
    cached = cached,
)

/** What the backend answers for a crop of a blank wall: a 200 with nothing in it. */
fun aBlankWall() = FrameTranslation(
    recognizedText = "",
    translatedText = "",
    regionHint = null,
    cached = false,
)

/** A region hint covering the middle band of whatever crop was uploaded. */
val MIDDLE_OF_THE_CROP = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.8f, height = 0.2f)

/** One crop, with bytes that are not a real JPEG — no test decodes them. */
fun aCropOf(region: NormalizedRect) = FrameCrop(jpeg = ByteArray(16) { 7 }, region = region)
