package com.genaijerry.mirror

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NormalizedRectTest {

    @Test
    fun a_union_covers_both_rectangles() {
        val left = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.2f, height = 0.1f)
        val right = NormalizedRect(x = 0.6f, y = 0.3f, width = 0.2f, height = 0.1f)

        assertRect(
            NormalizedRect(x = 0.1f, y = 0.3f, width = 0.7f, height = 0.2f),
            left.union(right),
        )
    }

    @Test
    fun the_union_of_no_rectangles_is_nothing() {
        assertNull(NormalizedRect.union(emptyList()))
    }

    @Test
    fun padding_grows_a_rectangle_on_every_side() {
        val text = NormalizedRect(x = 0.2f, y = 0.4f, width = 0.4f, height = 0.2f)

        val padded = text.padded(0.5f)

        assertEquals(0.0f, padded.x, TOLERANCE)
        assertEquals(0.3f, padded.y, TOLERANCE)
        assertEquals(0.8f, padded.width, TOLERANCE)
        assertEquals(0.4f, padded.height, TOLERANCE)
    }

    @Test
    fun padding_stops_at_the_edge_of_the_view() {
        val text = NormalizedRect(x = 0.0f, y = 0.9f, width = 1.0f, height = 0.1f)

        val padded = text.padded(0.5f)

        assertEquals(0.0f, padded.x, TOLERANCE)
        assertEquals(1.0f, padded.width, TOLERANCE)
        assertEquals(0.85f, padded.y, TOLERANCE)
        assertEquals(0.15f, padded.height, TOLERANCE)
    }

    @Test
    fun a_rectangle_reaching_past_the_view_is_cut_back() {
        val tooBig = NormalizedRect(x = -0.2f, y = 0.5f, width = 1.5f, height = 0.9f)

        val inView = tooBig.clampedToView()

        assertEquals(0.0f, inView.x, TOLERANCE)
        assertEquals(1.0f, inView.width, TOLERANCE)
        assertEquals(0.5f, inView.y, TOLERANCE)
        assertEquals(0.5f, inView.height, TOLERANCE)
    }

    @Test
    fun the_middle_of_the_view_lies_inside_the_view() {
        assertRect(NormalizedRect.CENTRE, NormalizedRect.CENTRE.clampedToView())
    }

    @Test
    fun a_region_hint_becomes_a_place_in_the_camera_view() {
        val crop = NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.2f)
        val hint = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.8f, height = 0.2f)

        assertRect(
            NormalizedRect(x = 0.25f, y = 0.58f, width = 0.4f, height = 0.04f),
            crop.inside(hint),
        )
    }

    @Test
    fun where_a_rectangle_sits_inside_another_survives_the_trip_back() {
        val crop = NormalizedRect(x = 0.2f, y = 0.5f, width = 0.5f, height = 0.2f)
        val hint = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.8f, height = 0.2f)

        assertRect(hint, crop.fractionOf(crop.inside(hint)))
    }

    @Test
    fun a_rectangle_with_no_area_has_nothing_to_measure_against() {
        val nothing = NormalizedRect(x = 0.5f, y = 0.5f, width = 0f, height = 0f)

        assertNull(nothing.fractionOf(NormalizedRect.CENTRE))
    }

    private companion object {
        const val TOLERANCE = RECT_TOLERANCE
    }
}
