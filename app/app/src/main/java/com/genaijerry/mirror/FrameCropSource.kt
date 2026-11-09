package com.genaijerry.mirror

/**
 * The newest camera frame, cut down to the part the text sits in.
 *
 * The camera is a parameter rather than something the refresh cycle reaches
 * for, so the unit tests hand it their own frames.
 */
fun interface FrameCropSource {
    /**
     * The newest frame cropped to [region], or null when no frame has arrived
     * yet — which is what the first moment after the camera starts looks like.
     */
    fun crop(region: NormalizedRect): FrameCrop?
}
