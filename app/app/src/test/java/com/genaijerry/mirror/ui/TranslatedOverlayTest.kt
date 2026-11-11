package com.genaijerry.mirror.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.DpRect
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.genaijerry.mirror.NormalizedRect
import com.genaijerry.mirror.TranslatedOverlay
import kotlin.math.abs
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * What the overlay draws, and where. The place is the point of it: the
 * translation sits on the words in the camera view, not in a panel at the edge
 * of the screen (ST-1).
 */
@RunWith(AndroidJUnit4::class)
class TranslatedOverlayTest {

    @get:Rule
    val compose = createComposeRule()

    private fun overlay(showing: TranslatedOverlay?) {
        compose.setContent {
            MirrorTheme {
                Box(modifier = Modifier.fillMaxSize()) { TranslatedOverlayLayer(showing) }
            }
        }
    }

    private fun drawnOverlay() =
        compose.onNodeWithTag(TranslatedOverlayTags.TEXT).getUnclippedBoundsInRoot()

    @Test
    fun nothing_is_drawn_before_the_first_translation_arrives() {
        overlay(null)

        compose.onNodeWithTag(TranslatedOverlayTags.TEXT).assertDoesNotExist()
    }

    @Test
    fun the_translation_is_drawn_over_the_camera() {
        overlay(TranslatedOverlay(text = "Kerala", region = BAND_ACROSS_THE_MIDDLE))

        compose.onNodeWithTag(TranslatedOverlayTags.TEXT).assertIsDisplayed()
        compose.onNodeWithText("Kerala").assertIsDisplayed()
    }

    @Test
    fun the_translation_sits_at_the_place_the_text_was_read() {
        overlay(TranslatedOverlay(text = "Kerala", region = BAND_ACROSS_THE_MIDDLE))

        val view = compose.onRoot().getUnclippedBoundsInRoot()
        val drawn = drawnOverlay()

        // A fifth of the way across and halfway down the view, as the region
        // says — not pinned to an edge, which is what a panel would be.
        assertNear(view.widthDp * 0.2f, drawn.left.value)
        assertNear(view.heightDp * 0.5f, drawn.top.value)
        assertNear(view.widthDp * 0.6f, drawn.widthDp)
        assertTrue("the overlay has no height at all", drawn.heightDp > 0f)
    }

    @Test
    fun a_translation_of_a_word_in_the_corner_is_still_wide_enough_to_read() {
        val corner = NormalizedRect(x = 0.9f, y = 0.1f, width = 0.05f, height = 0.03f)

        overlay(TranslatedOverlay(text = "A long sentence about Kerala", region = corner))

        val view = compose.onRoot().getUnclippedBoundsInRoot()
        val drawn = drawnOverlay()
        // A third of a view is wide enough for a sentence; a twentieth is not.
        assertTrue("the overlay is as narrow as the word was", drawn.widthDp > view.widthDp * 0.3f)
        assertTrue(
            "the overlay runs off the right-hand edge of the view",
            drawn.right.value <= view.right.value + TOLERANCE_DP,
        )
        compose.onNodeWithText("A long sentence about Kerala").assertIsDisplayed()
    }

    private fun assertNear(expected: Float, actual: Float) = assertTrue(
        "expected about $expected, found $actual",
        abs(expected - actual) <= TOLERANCE_DP,
    )

    private companion object {
        /** A fifth in from the left, halfway down, most of the way across. */
        val BAND_ACROSS_THE_MIDDLE =
            NormalizedRect(x = 0.2f, y = 0.5f, width = 0.6f, height = 0.1f)

        /** Rounding to whole pixels and back lands within a density step. */
        const val TOLERANCE_DP = 1.5f
    }
}

/**
 * How wide and tall a measured rectangle is, in dp.
 *
 * `DpRect` gives its four sides and no sizes, and every assertion above is
 * about a size.
 */
private val DpRect.widthDp: Float get() = (right - left).value
private val DpRect.heightDp: Float get() = (bottom - top).value
