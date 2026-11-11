package com.genaijerry.mirror

/**
 * A rectangle inside the camera view, measured in fractions of the view
 * rather than pixels: 0 is the left or top edge, 1 the right or bottom one.
 *
 * Fractions, not pixels, because the same rectangle has to mean the same
 * thing in three sizes — the analysis frame it was found in, the image sent
 * to the backend, and the preview the overlay is drawn on. The backend's
 * region hint uses the same 0–1 convention (see the design's API contract).
 */
data class NormalizedRect(
    val x: Float,
    val y: Float,
    val width: Float,
    val height: Float,
) {
    val right: Float get() = x + width
    val bottom: Float get() = y + height

    /** The smallest rectangle holding both this one and [other]. */
    fun union(other: NormalizedRect): NormalizedRect {
        val left = minOf(x, other.x)
        val top = minOf(y, other.y)
        return NormalizedRect(
            x = left,
            y = top,
            width = maxOf(right, other.right) - left,
            height = maxOf(bottom, other.bottom) - top,
        )
    }

    /**
     * This rectangle grown by [fraction] of its own size on every side, so a
     * crop keeps the letters' edges and the space around them. Growing past
     * the view's edges is cut back by [clampedToView].
     */
    fun padded(fraction: Float): NormalizedRect {
        val horizontal = width * fraction
        val vertical = height * fraction
        return NormalizedRect(
            x = x - horizontal,
            y = y - vertical,
            width = width + horizontal * 2,
            height = height + vertical * 2,
        ).clampedToView()
    }

    /**
     * The part of this rectangle that [part] covers, where [part] is measured
     * in fractions of this one rather than of the view.
     *
     * This is how the backend's region hint becomes a place in the camera
     * view: the hint is fractions of the crop that was uploaded, and the
     * crop's own rectangle is fractions of the view.
     */
    fun inside(part: NormalizedRect): NormalizedRect =
        NormalizedRect(
            x = x + part.x * width,
            y = y + part.y * height,
            width = part.width * width,
            height = part.height * height,
        ).clampedToView()

    /**
     * Where [part] sits inside this rectangle, in fractions of this one — the
     * inverse of [inside], and null when this rectangle has no area to measure
     * against.
     *
     * The two together are what keep the overlay on the text while the phone
     * moves: take where the translated text sat inside the crop it came from,
     * and put it in the same place inside the crop the app would cut now.
     */
    fun fractionOf(part: NormalizedRect): NormalizedRect? {
        if (width <= 0f || height <= 0f) return null
        return NormalizedRect(
            x = (part.x - x) / width,
            y = (part.y - y) / height,
            width = part.width / width,
            height = part.height / height,
        )
    }

    /** This rectangle with anything outside the camera view cut away. */
    fun clampedToView(): NormalizedRect {
        val left = x.coerceIn(0f, 1f)
        val top = y.coerceIn(0f, 1f)
        return NormalizedRect(
            x = left,
            y = top,
            width = (right.coerceIn(0f, 1f) - left).coerceAtLeast(0f),
            height = (bottom.coerceIn(0f, 1f) - top).coerceAtLeast(0f),
        )
    }

    companion object {
        /**
         * The middle of the view: what the app sends when the detector finds
         * no text at all (design decision D4). It is nearly the whole width
         * and a band across the middle, because text a person is pointing at
         * tends to run across the frame.
         */
        val CENTRE = NormalizedRect(x = 0.05f, y = 0.3f, width = 0.9f, height = 0.4f)

        /** The smallest rectangle holding every rectangle in [rects]. */
        fun union(rects: List<NormalizedRect>): NormalizedRect? =
            rects.reduceOrNull { all, next -> all.union(next) }
    }
}
