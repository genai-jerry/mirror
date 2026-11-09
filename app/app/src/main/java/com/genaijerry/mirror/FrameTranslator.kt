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
 * What a refresh cycle hands its crop to.
 *
 * The refresh cycle's job ends here: it finds the text, crops it and passes it
 * on. Sending it to the backend and drawing the answer is the translated
 * overlay's job (the next task), which supplies the real implementation of
 * this interface. Until then [LoggingFrameTranslator] shows the cycle working.
 *
 * An implementation that fails tells the cycle so by throwing: the cycle
 * treats that as a finished-and-failed cycle and starts the next one on
 * schedule.
 */
fun interface FrameTranslator {
    suspend fun translate(crop: FrameCrop)
}
