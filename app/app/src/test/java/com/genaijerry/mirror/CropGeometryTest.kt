package com.genaijerry.mirror

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CropGeometryTest {

    @Test
    fun the_rectangle_in_pixels_follows_the_fractions() {
        val region = NormalizedRect(x = 0.25f, y = 0.5f, width = 0.5f, height = 0.25f)

        assertEquals(
            PixelRect(left = 160, top = 240, width = 320, height = 120),
            CropGeometry.pixelRect(region, frameWidth = 640, frameHeight = 480),
        )
    }

    @Test
    fun a_rectangle_reaching_past_the_frame_stays_inside_it() {
        val region = NormalizedRect(x = 0.9f, y = 0.9f, width = 0.5f, height = 0.5f)

        val rect = CropGeometry.pixelRect(region, frameWidth = 640, frameHeight = 480)

        assertTrue(rect.left + rect.width <= 640)
        assertTrue(rect.top + rect.height <= 480)
    }

    @Test
    fun there_is_always_at_least_one_pixel_to_crop() {
        val nothing = NormalizedRect(x = 0.5f, y = 0.5f, width = 0f, height = 0f)

        val rect = CropGeometry.pixelRect(nothing, frameWidth = 640, frameHeight = 480)

        assertEquals(1, rect.width)
        assertEquals(1, rect.height)
    }

    @Test
    fun a_large_crop_is_shrunk_to_the_long_edge_the_backend_is_sent() {
        val size = CropGeometry.downscaled(width = 4000, height = 2000)

        assertEquals(CropGeometry.MAX_LONG_EDGE_PX, size.width)
        assertEquals(640, size.height)
    }

    @Test
    fun a_tall_crop_is_shrunk_by_its_own_long_edge() {
        val size = CropGeometry.downscaled(width = 1000, height = 2560)

        assertEquals(CropGeometry.MAX_LONG_EDGE_PX, size.height)
        assertEquals(500, size.width)
    }

    @Test
    fun a_crop_already_small_enough_is_sent_as_it_is() {
        val size = CropGeometry.downscaled(width = 800, height = 200)

        assertEquals(PixelSize(width = 800, height = 200), size)
    }
}
