package com.genaijerry.mirror

/** A rectangle in whole pixels of one camera frame. */
data class PixelRect(val left: Int, val top: Int, val width: Int, val height: Int)

/** A size in whole pixels. */
data class PixelSize(val width: Int, val height: Int)

/**
 * The arithmetic of turning an anchor rectangle into the picture that is sent
 * to the backend: where to cut, and how far to shrink what was cut.
 *
 * It is plain arithmetic on purpose — no camera and no bitmap — so the numbers
 * the design fixes are pinned by unit tests rather than by a device.
 */
object CropGeometry {
    /**
     * How much space is kept around the text, as a fraction of the text's own
     * size. Letters sit right on the edge of what a detector reports, and
     * recognition reads a tight crop badly.
     */
    const val PADDING_FRACTION = 0.08f

    /**
     * The longest edge of the picture sent to the backend. Larger costs
     * upload time on a mobile connection and buys no accuracy on a headline.
     */
    const val MAX_LONG_EDGE_PX = 1280

    /** JPEG quality of that picture: small, and still sharp enough to read. */
    const val JPEG_QUALITY = 80

    /**
     * The part of a frame [frameWidth] × [frameHeight] pixels that [region]
     * covers, never smaller than one pixel so there is always something to
     * crop.
     */
    fun pixelRect(region: NormalizedRect, frameWidth: Int, frameHeight: Int): PixelRect {
        val inView = region.clampedToView()
        val left = (inView.x * frameWidth).toInt().coerceIn(0, maxOf(frameWidth - 1, 0))
        val top = (inView.y * frameHeight).toInt().coerceIn(0, maxOf(frameHeight - 1, 0))
        return PixelRect(
            left = left,
            top = top,
            width = (inView.width * frameWidth).toInt().coerceIn(1, frameWidth - left),
            height = (inView.height * frameHeight).toInt().coerceIn(1, frameHeight - top),
        )
    }

    /**
     * [width] × [height] shrunk so that its longest edge is at most
     * [maxLongEdge], keeping its shape. A picture already that small is left
     * alone — enlarging it would add no detail and cost upload time.
     */
    fun downscaled(width: Int, height: Int, maxLongEdge: Int = MAX_LONG_EDGE_PX): PixelSize {
        val longEdge = maxOf(width, height)
        if (longEdge <= maxLongEdge) return PixelSize(width, height)
        val scale = maxLongEdge.toFloat() / longEdge
        return PixelSize(
            width = (width * scale).toInt().coerceAtLeast(1),
            height = (height * scale).toInt().coerceAtLeast(1),
        )
    }
}
