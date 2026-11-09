package com.genaijerry.mirror.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

/**
 * One dark theme, always. The screen is mostly camera, and a light surface
 * around a live view is hard to read in daylight.
 */
@Composable
fun MirrorTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = darkColorScheme(), content = content)
}
