package com.genaijerry.mirror

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TextRegionTrackerTest {

    private val heard = mutableListOf<TextAnchor?>()
    private val tracker = TextRegionTracker(onAnchorChanged = { heard += it })

    @Test
    fun nothing_is_anchored_before_the_first_frame() {
        assertNull(tracker.anchor)
    }

    @Test
    fun the_anchor_covers_every_block_of_text_the_detector_found() {
        tracker.onTextLocated(
            listOf(
                NormalizedRect(x = 0.1f, y = 0.4f, width = 0.2f, height = 0.1f),
                NormalizedRect(x = 0.6f, y = 0.3f, width = 0.2f, height = 0.1f),
            ),
        )

        val anchor = requireNotNull(tracker.anchor)
        assertRect(NormalizedRect(x = 0.1f, y = 0.3f, width = 0.7f, height = 0.2f), anchor.region)
        assertTrue(anchor.detected)
    }

    @Test
    fun an_empty_rectangle_is_not_text() {
        tracker.onTextLocated(listOf(NormalizedRect(x = 0.5f, y = 0.5f, width = 0f, height = 0f)))

        assertNull(tracker.anchor)
    }

    @Test
    fun one_frame_with_no_text_leaves_the_anchor_where_it_was() {
        val text = NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.1f)
        tracker.onTextLocated(listOf(text))

        tracker.onTextLocated(emptyList())

        assertRect(text, requireNotNull(tracker.anchor).region)
        assertTrue(requireNotNull(tracker.anchor).detected)
    }

    @Test
    fun the_middle_of_the_view_becomes_the_anchor_after_two_frames_with_no_text() {
        tracker.onTextLocated(
            listOf(NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.1f)),
        )

        tracker.onTextLocated(emptyList())
        tracker.onTextLocated(emptyList())

        val anchor = requireNotNull(tracker.anchor)
        assertRect(NormalizedRect.CENTRE, anchor.region)
        assertFalse(anchor.detected)
    }

    @Test
    fun the_middle_of_the_view_is_the_anchor_even_when_text_was_never_found() {
        tracker.onTextLocated(emptyList())
        tracker.onTextLocated(emptyList())

        assertRect(NormalizedRect.CENTRE, requireNotNull(tracker.anchor).region)
    }

    @Test
    fun text_found_again_takes_the_anchor_back_from_the_middle_of_the_view() {
        tracker.onTextLocated(emptyList())
        tracker.onTextLocated(emptyList())
        val text = NormalizedRect(x = 0.3f, y = 0.2f, width = 0.4f, height = 0.1f)

        tracker.onTextLocated(listOf(text))

        assertRect(text, requireNotNull(tracker.anchor).region)
        assertTrue(requireNotNull(tracker.anchor).detected)
    }

    @Test
    fun the_anchor_is_reported_only_when_it_moves() {
        val text = NormalizedRect(x = 0.3f, y = 0.2f, width = 0.4f, height = 0.1f)

        tracker.onTextLocated(listOf(text))
        tracker.onTextLocated(listOf(text))
        tracker.onTextLocated(listOf(text))

        assertEquals(1, heard.size)
        assertRect(text, requireNotNull(heard.single()).region)
    }

    @Test
    fun forgetting_the_text_clears_the_anchor() {
        tracker.onTextLocated(
            listOf(NormalizedRect(x = 0.3f, y = 0.2f, width = 0.4f, height = 0.1f)),
        )

        tracker.forget()

        assertNull(tracker.anchor)
        assertEquals(2, heard.size)
    }

    @Test
    fun forgetting_the_text_starts_the_count_of_empty_frames_again() {
        tracker.onTextLocated(emptyList())
        tracker.forget()

        tracker.onTextLocated(emptyList())

        assertNull(tracker.anchor)
    }
}
