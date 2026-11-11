package com.genaijerry.mirror

import java.io.IOException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The one rule the graceful-degradation scenarios rest on: the last good
 * translation stays on screen until a better one arrives — through a pending
 * cycle, through an outage, through a refused language pair — and only a crop
 * with no text in it clears it.
 */
class TranslatedOverlayStateTest {

    private val state = TranslatedOverlayState()

    @Test
    fun the_translation_is_drawn_where_the_backend_read_the_text() {
        val crop = aCropOf(NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.2f))

        state.show(crop, aTranslationOf("കേരളം", "Kerala", MIDDLE_OF_THE_CROP))

        assertEquals("Kerala", state.overlay?.text)
        // The hint is fractions of the crop, so x is 0.2 + 0.1 × 0.5.
        assertRect(
            NormalizedRect(x = 0.25f, y = 0.58f, width = 0.4f, height = 0.04f),
            state.overlay?.region,
        )
    }

    @Test
    fun a_backend_that_cannot_say_where_the_text_was_points_at_the_whole_crop() {
        val crop = aCropOf(NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.2f))

        state.show(crop, aTranslationOf("കേരളം", "Kerala", regionHint = null))

        assertRect(crop.region, state.overlay?.region)
    }

    @Test
    fun nothing_is_drawn_before_the_first_cycle_has_answered() {
        assertNull(state.overlay)
    }

    @Test
    fun a_newer_translation_replaces_the_one_on_screen() {
        state.show(aCropOf(SOME_TEXT), aTranslationOf("ഒന്ന്", "One"))

        state.show(aCropOf(SOME_TEXT), aTranslationOf("രണ്ട്", "Two"))

        assertEquals("Two", state.overlay?.text)
    }

    @Test
    fun a_crop_with_no_text_in_it_clears_the_overlay() {
        state.show(aCropOf(SOME_TEXT), aTranslationOf("കേരളം", "Kerala"))

        state.show(aCropOf(SOME_TEXT), aBlankWall())

        assertNull(state.overlay)
    }

    @Test
    fun the_last_good_overlay_stays_while_the_next_cycle_is_still_running() {
        val tracker = TextRegionTracker()
        tracker.onTextLocated(listOf(SOME_TEXT))
        val showingMidCycle = mutableListOf<TranslatedOverlay?>()
        // Looks at the screen from inside a cycle: the crop has gone and the
        // answer has not come back, which is the moment ST-3 watches for.
        val translator = FrameTranslator {
            showingMidCycle += state.overlay
            aTranslationOf("കേരളം", "Kerala")
        }

        runBlocking { loopOver(tracker, translator).run(cycles = 3) }

        assertEquals(listOf(null, "Kerala", "Kerala"), showingMidCycle.map { it?.text })
        assertEquals("Kerala", state.overlay?.text)
    }

    @Test
    fun the_last_good_overlay_stays_through_a_backend_that_has_stopped_answering() {
        val tracker = TextRegionTracker()
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = FakeFrameTranslator(answer = aTranslationOf("കേരളം", "Kerala"))

        runBlocking {
            val loop = loopOver(tracker, translator)
            loop.run(cycles = 1)
            translator.failure = IOException("the backend is down")
            loop.run(cycles = 3)
        }

        assertEquals("Kerala", state.overlay?.text)
    }

    @Test
    fun the_overlay_catches_up_on_the_first_cycle_that_succeeds_again() {
        val tracker = TextRegionTracker()
        tracker.onTextLocated(listOf(SOME_TEXT))
        val translator = FakeFrameTranslator(
            answer = aTranslationOf("ഒന്ന്", "One"),
            failure = IOException("the backend is down"),
        )

        runBlocking {
            val loop = loopOver(tracker, translator)
            loop.run(cycles = 2)
            translator.failure = null
            translator.answer = aTranslationOf("രണ്ട്", "Two")
            loop.run(cycles = 1)
        }

        assertEquals("Two", state.overlay?.text)
    }

    @Test
    fun the_overlay_moves_with_the_text_while_the_phone_moves() {
        val anchor = NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.2f)
        state.show(
            aCropOf(anchor.padded(CropGeometry.PADDING_FRACTION)),
            aTranslationOf("കേരളം", "Kerala", MIDDLE_OF_THE_CROP),
        )
        val before = state.overlay!!.region

        // The same text, found a tenth of the view further right and down.
        val moved = NormalizedRect(x = 0.3f, y = 0.6f, width = 0.5f, height = 0.2f)
        state.reanchor(TextAnchor(region = moved, detected = true))

        val after = state.overlay!!.region
        assertEquals("Kerala", state.overlay?.text)
        assertEquals(before.x + 0.1f, after.x, RECT_TOLERANCE)
        assertEquals(before.y + 0.1f, after.y, RECT_TOLERANCE)
        assertEquals(before.width, after.width, RECT_TOLERANCE)
        assertEquals(before.height, after.height, RECT_TOLERANCE)
    }

    @Test
    fun losing_sight_of_the_text_leaves_the_overlay_where_it_was() {
        state.show(aCropOf(SOME_TEXT), aTranslationOf("കേരളം", "Kerala"))
        val before = state.overlay

        // Two frames with no text: the next crop is the middle of the view, but
        // the words are not known to have moved there.
        state.reanchor(TextAnchor(region = NormalizedRect.CENTRE, detected = false))

        assertEquals(before, state.overlay)
    }

    @Test
    fun the_camera_stopping_clears_the_overlay() {
        state.show(aCropOf(SOME_TEXT), aTranslationOf("കേരളം", "Kerala"))

        state.reanchor(null)

        assertNull(state.overlay)
    }

    @Test
    fun an_anchor_arriving_before_any_translation_draws_nothing() {
        state.reanchor(TextAnchor(region = SOME_TEXT, detected = true))

        assertNull(state.overlay)
    }

    /** The real refresh cycle, wired to the overlay the way the screen wires it. */
    private fun loopOver(tracker: TextRegionTracker, translator: FrameTranslator) =
        RefreshLoop(
            tracker = tracker,
            crops = { region -> aCropOf(region) },
            translator = translator,
            clock = { 0L },
            pause = {},
            onCycleTranslated = state::show,
        )

    private companion object {
        val SOME_TEXT = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.8f, height = 0.1f)
    }
}
