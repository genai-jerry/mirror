package com.genaijerry.mirror

import android.util.Log

private const val TAG = "FrameTranslator"

/**
 * Writes each crop to the log instead of sending it anywhere.
 *
 * This is what the camera screen uses until the translated overlay task
 * supplies the real client: the detection and the refresh cycle are then
 * observable on a phone — one log line every five seconds, saying how big the
 * crop was and where in the camera view the text sits — without any backend
 * call.
 */
object LoggingFrameTranslator : FrameTranslator {
    override suspend fun translate(crop: FrameCrop) {
        Log.i(TAG, "A refresh cycle cropped the text: $crop")
    }
}
