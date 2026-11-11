package com.genaijerry.mirror

/**
 * Where the app currently believes the text sits in the camera view.
 *
 * @param region the rectangle the next crop is taken from, and the one the
 *   overlay is anchored to.
 * @param detected true when the detector found text there, false when this is
 *   the middle-of-the-view fallback.
 */
data class TextAnchor(val region: NormalizedRect, val detected: Boolean)

/**
 * Keeps track of where the text is, from what the on-device detector reports
 * for each camera frame.
 *
 * The detector runs far more often than the refresh cycle, which is what lets
 * the overlay follow the text while a phone moves (design decision D4). Two
 * rules make it steady:
 *
 *  - One empty frame changes nothing. A hand wobble or a moment of blur
 *    should not throw the overlay away.
 *  - After [emptyFramesBeforeFallback] empty frames in a row the anchor
 *    becomes the middle of the view, so the app keeps translating even where
 *    the detector cannot find the script at all — the risk design decision D4
 *    names.
 *
 * It holds no Android types, so the unit tests drive it directly.
 */
class TextRegionTracker(
    private val emptyFramesBeforeFallback: Int = DEFAULT_EMPTY_FRAMES_BEFORE_FALLBACK,
    private val onAnchorChanged: (TextAnchor?) -> Unit = {},
) {
    @Volatile
    var anchor: TextAnchor? = null
        private set

    private var emptyFrames = 0

    /**
     * Report what the detector found in one frame: every text rectangle it
     * located, in camera-view fractions, or an empty list for a frame with no
     * text in it.
     */
    fun onTextLocated(regions: List<NormalizedRect>) {
        val found = NormalizedRect.union(regions.filter { it.width > 0f && it.height > 0f })
        if (found != null) {
            emptyFrames = 0
            moveTo(TextAnchor(region = found.clampedToView(), detected = true))
            return
        }

        emptyFrames++
        if (emptyFrames >= emptyFramesBeforeFallback) {
            moveTo(TextAnchor(region = NormalizedRect.CENTRE, detected = false))
        }
    }

    /** Forget where the text was — the camera stopped, or the screen closed. */
    fun forget() {
        emptyFrames = 0
        moveTo(null)
    }

    private fun moveTo(next: TextAnchor?) {
        if (next == anchor) return
        anchor = next
        onAnchorChanged(next)
    }

    companion object {
        /** Design decision D4: the fallback engages after two empty frames. */
        const val DEFAULT_EMPTY_FRAMES_BEFORE_FALLBACK = 2
    }
}
