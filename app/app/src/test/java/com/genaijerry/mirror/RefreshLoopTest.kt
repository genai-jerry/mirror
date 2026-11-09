package com.genaijerry.mirror

import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The refresh cycle's discipline (design decision D9), on a made-up clock: a
 * cycle at a time, five seconds apart, and a failure that stops nothing.
 */
class RefreshLoopTest {

    private val clock = TestClock()
    private val tracker = TextRegionTracker()
    private val cropsAsked = mutableListOf<NormalizedRect>()

    private val recordingCrops = FrameCropSource { region ->
        cropsAsked += region
        FrameCrop(jpeg = ByteArray(8), region = region)
    }

    @Test
    fun five_seconds_pass_between_the_starts_of_two_cycles() {
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = RecordingTranslator(clock)

        runBlocking { loopWith(translator).run(cycles = 3) }

        assertEquals(listOf(0L, 5_000L, 10_000L), translator.startedAt)
    }

    @Test
    fun a_cycle_that_runs_long_is_followed_straight_away_by_the_next() {
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = RecordingTranslator(clock, takesMillis = 12_000L)

        runBlocking { loopWith(translator).run(cycles = 3) }

        assertEquals(listOf(0L, 12_000L, 24_000L), translator.startedAt)
        assertTrue("the loop should not have waited", clock.waits.isEmpty())
    }

    @Test
    fun only_one_cycle_is_ever_in_flight() {
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = RecordingTranslator(clock, takesMillis = 7_000L)

        runBlocking { loopWith(translator).run(cycles = 4) }

        assertEquals(1, translator.mostAtOnce)
    }

    @Test
    fun a_cycle_that_fails_does_not_stop_the_next_one() {
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = RecordingTranslator(clock, fails = true)
        val failures = mutableListOf<Throwable>()

        runBlocking { loopWith(translator, onCycleFailed = { failures += it }).run(cycles = 3) }

        assertEquals(listOf(0L, 5_000L, 10_000L), translator.startedAt)
        assertEquals(3, failures.size)
    }

    @Test
    fun the_crop_keeps_space_around_the_text() {
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = RecordingTranslator(clock)

        runBlocking { loopWith(translator).run(cycles = 1) }

        assertEquals(1, cropsAsked.size)
        assertRect(SOME_TEXT.padded(CropGeometry.PADDING_FRACTION), cropsAsked.single())
    }

    @Test
    fun the_middle_of_the_view_is_cropped_after_two_frames_with_no_text() {
        tracker.onTextLocated(emptyList())
        tracker.onTextLocated(emptyList())
        val translator = RecordingTranslator(clock)

        runBlocking { loopWith(translator).run(cycles = 1) }

        assertEquals(1, cropsAsked.size)
        assertRect(NormalizedRect.CENTRE.padded(CropGeometry.PADDING_FRACTION), cropsAsked.single())
        assertEquals(1, translator.startedAt.size)
    }

    @Test
    fun nothing_is_sent_while_the_detector_has_seen_no_frame_at_all() {
        val translator = RecordingTranslator(clock)

        runBlocking { loopWith(translator).run(cycles = 3) }

        assertTrue(cropsAsked.isEmpty())
        assertTrue(translator.startedAt.isEmpty())
    }

    @Test
    fun nothing_is_sent_while_the_camera_has_no_frame_to_crop() {
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = RecordingTranslator(clock)

        runBlocking { loopWith(translator, crops = { null }).run(cycles = 2) }

        assertTrue(translator.startedAt.isEmpty())
    }

    private fun loopWith(
        translator: FrameTranslator,
        crops: FrameCropSource = recordingCrops,
        onCycleFailed: (Throwable) -> Unit = {},
    ) = RefreshLoop(
        tracker = tracker,
        crops = crops,
        translator = translator,
        clock = { clock.now },
        pause = { clock.waitFor(it) },
        onCycleFailed = onCycleFailed,
    )

    /** A clock the test moves itself, so the whole loop runs in no time. */
    private class TestClock {
        var now = 0L
        val waits = mutableListOf<Long>()

        fun waitFor(millis: Long) {
            waits += millis
            now += millis
        }
    }

    private class RecordingTranslator(
        private val clock: TestClock,
        private val takesMillis: Long = 0L,
        private val fails: Boolean = false,
    ) : FrameTranslator {
        val startedAt = mutableListOf<Long>()
        var mostAtOnce = 0
            private set

        private var inFlight = 0

        override suspend fun translate(crop: FrameCrop) {
            startedAt += clock.now
            inFlight++
            mostAtOnce = maxOf(mostAtOnce, inFlight)
            try {
                clock.now += takesMillis
                if (fails) error("the backend was not reachable")
            } finally {
                inFlight--
            }
        }
    }

    private companion object {
        val SOME_TEXT = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.6f, height = 0.1f)
    }
}
