package com.genaijerry.mirror

/**
 * One cropped picture of the text, ready to be sent on.
 *
 * @param jpeg the crop, JPEG encoded.
 * @param region where the crop was taken from in the camera view, in
 *   fractions of the view — this is what the overlay is anchored to.
 */
class FrameCrop(val jpeg: ByteArray, val region: NormalizedRect) {
    override fun toString(): String = "FrameCrop(${jpeg.size} bytes, $region)"
}

/**
 * What the backend answered about one crop.
 *
 * This is the 200 body of `POST /v1/frames/translate` (the design's API
 * contract), with the region hint kept in the same fractions-of-1 convention
 * the rest of the app uses — fractions of the crop that was uploaded, though,
 * not of the camera view.
 *
 * @param regionHint where in the crop the text was read, or null when the
 *   backend read no text at all. A crop of a blank wall comes back with both
 *   texts empty, no hint and a 200: it is an answer, not a failure.
 */
data class FrameTranslation(
    val recognizedText: String,
    val translatedText: String,
    val regionHint: NormalizedRect?,
    val cached: Boolean,
) {
    /** True when the backend read no text in the crop — the blank wall. */
    val isBlank: Boolean get() = translatedText.isBlank()
}

/**
 * What a refresh cycle hands its crop to: the backend, through
 * [BackendFrameTranslator].
 *
 * An implementation that fails tells the cycle so by throwing: the cycle
 * treats that as a finished-and-failed cycle and starts the next one on
 * schedule. Keeping the last good translation on screen through that failure
 * is [TranslatedOverlayState]'s rule, not this interface's.
 */
fun interface FrameTranslator {
    suspend fun translate(crop: FrameCrop): FrameTranslation
}
