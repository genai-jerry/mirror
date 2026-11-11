package com.genaijerry.mirror

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * The overlay on screen right now: what it says, and where in the camera view
 * it sits.
 */
data class TranslatedOverlay(val text: String, val region: NormalizedRect)

/**
 * What the camera screen draws over the live view, and the one rule that makes
 * it feel like a translation rather than a loading screen: **the last good
 * translation stays until a better one arrives.**
 *
 * There are only four things that ever happen to it:
 *
 *  - A cycle **finishes with text.** That text replaces the overlay, at the
 *    place the backend said it read it.
 *  - A cycle **is still running.** Nothing happens — which is the whole point.
 *    No blank, no spinner, no error.
 *  - A cycle **fails**: the backend is down, slow, out of recognition
 *    allowance, or refuses the language pair. Nothing happens here either,
 *    because nothing tells this class about a failure at all. The overlay
 *    outlives the outage and catches up on the first cycle that succeeds.
 *  - A cycle **finishes with no text** — the camera is on a blank wall. That
 *    clears the overlay, because there is nothing there to translate any more.
 *
 * Between cycles the detector keeps saying where the text has moved to, and
 * [reanchor] moves the overlay with it, so it stays on the words while the
 * phone is in a hand.
 */
class TranslatedOverlayState {

    var overlay: TranslatedOverlay? by mutableStateOf(null)
        private set

    /**
     * The rectangle the showing overlay's crop was cut from. [reanchor]
     * measures the move against it, so it is kept beside the overlay and
     * replaced whenever the overlay moves.
     */
    private var cropWhenTranslated: NormalizedRect? = null

    /** A cycle finished: show what the backend read, or clear a blank wall. */
    fun show(crop: FrameCrop, translation: FrameTranslation) {
        if (translation.isBlank) {
            forget()
            return
        }
        cropWhenTranslated = crop.region
        overlay = TranslatedOverlay(
            text = translation.translatedText,
            // No hint means the backend read text but could not say where in
            // the crop: the crop itself is then the best place to point at.
            region = translation.regionHint?.let { crop.region.inside(it) } ?: crop.region,
        )
    }

    /**
     * The detector has moved the anchor: move the overlay with it, keeping it
     * where it sat inside the crop.
     *
     * The fallback anchor — the middle of the view, after two frames with no
     * text — moves nothing. The detector has lost the text rather than found
     * it somewhere else, so dragging the words to the middle of the screen
     * would be a worse guess than leaving them where they were last seen.
     *
     * A forgotten anchor means the camera has stopped, and an overlay anchored
     * to nothing is stale, so that clears it.
     */
    fun reanchor(anchor: TextAnchor?) {
        if (anchor == null) {
            forget()
            return
        }
        if (!anchor.detected) return
        val showing = overlay ?: return
        val from = cropWhenTranslated ?: return
        // Where the crop would be cut now: the same padding the refresh cycle
        // applies, so the two rectangles are the same kind of thing.
        val to = anchor.region.padded(CropGeometry.PADDING_FRACTION)
        val moved = from.fractionOf(showing.region)?.let { to.inside(it) } ?: return
        cropWhenTranslated = to
        overlay = showing.copy(region = moved)
    }

    /** Draw nothing: the camera stopped, or there is no text to translate. */
    fun forget() {
        cropWhenTranslated = null
        overlay = null
    }
}
