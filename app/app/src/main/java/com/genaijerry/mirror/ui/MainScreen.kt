package com.genaijerry.mirror.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.genaijerry.mirror.R

/** Test tags the unit tests address the screen by. */
object MainScreenTags {
    const val CAMERA = "main.camera"
    const val STARTING = "main.starting"
    const val PERMISSION_DENIED = "main.permissionDenied"
}

/**
 * The whole screen, with no state of its own.
 *
 * Everything that touches the system — asking for the camera permission,
 * opening the settings app, running CameraX — is passed in, which is what
 * lets the unit tests drive the screen without a device.
 *
 * @param cameraContent what fills the screen once the camera may be used.
 *   Later tasks draw the translated overlay on top of it.
 */
@Composable
fun MainScreen(
    status: CameraPermissionStatus,
    onRequestPermission: () -> Unit,
    onOpenSettings: () -> Unit,
    modifier: Modifier = Modifier,
    cameraContent: @Composable () -> Unit = { CameraPreview(Modifier.fillMaxSize()) },
) {
    Surface(modifier = modifier.fillMaxSize(), color = MaterialTheme.colorScheme.scrim) {
        when (status) {
            CameraPermissionStatus.NotAsked -> {
                // Ask once, when the screen first appears.
                LaunchedEffect(Unit) { onRequestPermission() }
                CenteredMessage(
                    tag = MainScreenTags.STARTING,
                    text = stringResource(R.string.camera_starting),
                )
            }

            CameraPermissionStatus.Granted ->
                Box(modifier = Modifier.fillMaxSize().testTag(MainScreenTags.CAMERA)) {
                    cameraContent()
                }

            CameraPermissionStatus.Denied ->
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(24.dp)
                        .testTag(MainScreenTags.PERMISSION_DENIED),
                    verticalArrangement = Arrangement.Center,
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    Text(
                        text = stringResource(R.string.camera_permission_title),
                        style = MaterialTheme.typography.titleLarge,
                    )
                    Text(
                        text = stringResource(R.string.camera_permission_body),
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.padding(top = 12.dp, bottom = 24.dp),
                    )
                    Button(onClick = onOpenSettings) {
                        Text(stringResource(R.string.camera_permission_open_settings))
                    }
                }
        }
    }
}

@Composable
private fun CenteredMessage(tag: String, text: String) {
    Box(
        modifier = Modifier.fillMaxSize().testTag(tag),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = text, style = MaterialTheme.typography.bodyLarge)
    }
}
