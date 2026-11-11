package com.genaijerry.mirror.ui

import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.genaijerry.mirror.TranslatedOverlay

/** Test tags the unit tests address the overlay by. */
object TranslatedOverlayTags {
    const val TEXT = "overlay.text"
}

/**
 * How much of the view's width the overlay takes at the very least.
 *
 * A region can be a short word in a corner, and a translation of it is usually
 * longer than the word was. Below this the overlay would be a column of one
 * letter per line.
 */
private const val MINIMUM_WIDTH_FRACTION = 0.35f

/** How solid the backing behind the words is, over a live camera view. */
private const val BACKING_ALPHA = 0.72f

/**
 * The translated text, drawn over the live camera view where the source text
 * sits.
 *
 * The place comes from the camera view itself, not from a panel at the edge of
 * the screen: the region is in fractions of the view (see `NormalizedRect`),
 * so this turns those fractions into whatever space the preview is actually
 * filling. It is drawn on a dark backing, because white words straight onto a
 * daylit scene cannot be read.
 *
 * Nothing at all is drawn when there is no overlay — before the first cycle
 * has answered, and on a blank wall.
 */
@Composable
fun TranslatedOverlayLayer(overlay: TranslatedOverlay?, modifier: Modifier = Modifier) {
    val showing = overlay ?: return
    BoxWithConstraints(modifier = modifier.fillMaxSize()) {
        val region = showing.region
        val width = maxWidth * region.width.coerceIn(MINIMUM_WIDTH_FRACTION, 1f)
        // Kept inside the view: a region at the right-hand edge would otherwise
        // push a wider translation off the screen.
        val left = (maxWidth * region.x.coerceIn(0f, 1f))
            .coerceAtMost((maxWidth - width).coerceAtLeast(0.dp))
        val top = maxHeight * region.y.coerceIn(0f, 1f)

        Surface(
            modifier = Modifier
                .offset(x = left, y = top)
                .width(width)
                .testTag(TranslatedOverlayTags.TEXT),
            color = Color.Black.copy(alpha = BACKING_ALPHA),
            shape = MaterialTheme.shapes.small,
        ) {
            Text(
                text = showing.text,
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                style = MaterialTheme.typography.titleMedium,
                color = Color.White,
            )
        }
    }
}
