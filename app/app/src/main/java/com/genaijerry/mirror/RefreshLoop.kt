package com.genaijerry.mirror

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay

/**
 * The cycle that keeps the overlay up to date, with nobody tapping anything.
 *
 * One cycle is: take the anchor the [tracker] holds, crop the newest camera
 * frame to it, and hand the crop to the [translator]. Design decision D9 sets
 * the two rules that matter:
 *
 *  - **One cycle at a time.** The next one starts when this one has finished
 *    or failed, never beside it. The loop is one coroutine doing one thing
 *    after another, so that is true by construction.
 *  - **At least [minimumIntervalMillis] between starts.** One phone must not
 *    drain the recognition budget the whole estate shares. A cycle that takes
 *    longer than the interval is followed immediately by the next one; a quick
 *    cycle waits out the rest of the interval.
 *
 * A cycle that ends is a cycle the loop reports and then leaves alone: one
 * that answered goes to [onCycleTranslated], one that threw goes to
 * [onCycleFailed], and the loop carries on either way. What to put on screen
 * for each is the overlay's rule, not this loop's.
 *
 * @param clock the source of "now", in milliseconds. A test supplies its own.
 * @param pause how the loop waits. A test supplies its own, so the whole loop
 *   runs in no time at all.
 */
class RefreshLoop(
    private val tracker: TextRegionTracker,
    private val crops: FrameCropSource,
    private val translator: FrameTranslator,
    private val minimumIntervalMillis: Long = DEFAULT_INTERVAL_MILLIS,
    private val clock: () -> Long = System::currentTimeMillis,
    private val pause: suspend (Long) -> Unit = { delay(it) },
    private val onCycleTranslated: (FrameCrop, FrameTranslation) -> Unit = { _, _ -> },
    private val onCycleFailed: (Throwable) -> Unit = {},
) {
    /**
     * Run cycles until the coroutine running this is cancelled, or until
     * [cycles] of them have been run.
     *
     * The default runs for as long as the camera screen is open, which is
     * what that screen wants. The unit tests ask for a few.
     */
    suspend fun run(cycles: Int = Int.MAX_VALUE) {
        var lastStart: Long? = null
        repeat(cycles) {
            lastStart?.let { previous ->
                val remaining = previous + minimumIntervalMillis - clock()
                if (remaining > 0) pause(remaining)
            }
            lastStart = clock()
            runOneCycle()
        }
    }

    private suspend fun runOneCycle() {
        try {
            val anchor = tracker.anchor ?: return
            val crop = crops.crop(anchor.region.padded(CropGeometry.PADDING_FRACTION)) ?: return
            onCycleTranslated(crop, translator.translate(crop))
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (failure: Throwable) {
            onCycleFailed(failure)
        }
    }

    companion object {
        /** Design decision D9: about five seconds between cycles. */
        const val DEFAULT_INTERVAL_MILLIS = 5_000L
    }
}
