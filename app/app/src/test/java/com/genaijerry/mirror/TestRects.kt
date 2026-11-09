package com.genaijerry.mirror

import org.junit.Assert.assertEquals

/**
 * How close two fractions have to be to count as the same rectangle.
 *
 * Cutting a rectangle back to the view's edges re-derives its width from its
 * two sides, and that arithmetic lands a few millionths away from the number a
 * person would write down. Rectangles are therefore compared with a
 * tolerance, never with equals.
 */
internal const val RECT_TOLERANCE = 0.0001f

/** Fail unless [actual] is [expected], to within [RECT_TOLERANCE]. */
internal fun assertRect(expected: NormalizedRect, actual: NormalizedRect?) {
    val found = requireNotNull(actual) { "expected $expected, found no rectangle at all" }
    assertEquals("x of $found", expected.x, found.x, RECT_TOLERANCE)
    assertEquals("y of $found", expected.y, found.y, RECT_TOLERANCE)
    assertEquals("width of $found", expected.width, found.width, RECT_TOLERANCE)
    assertEquals("height of $found", expected.height, found.height, RECT_TOLERANCE)
}
