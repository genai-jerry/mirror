package com.genaijerry.mirror.ui

import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainScreenTest {

    @get:Rule
    val compose = createComposeRule()

    @Test
    fun the_screen_asks_for_the_camera_exactly_once_when_it_opens() {
        var asked = 0

        compose.setContent {
            MirrorTheme {
                MainScreen(
                    status = CameraPermissionStatus.NotAsked,
                    onRequestPermission = { asked++ },
                    onOpenSettings = {},
                    cameraContent = {},
                )
            }
        }
        compose.waitForIdle()

        assertEquals(1, asked)
        compose.onNodeWithTag(MainScreenTags.STARTING).assertIsDisplayed()
    }

    @Test
    fun the_camera_view_fills_the_screen_once_the_camera_is_allowed() {
        compose.setContent {
            MirrorTheme {
                MainScreen(
                    status = CameraPermissionStatus.Granted,
                    onRequestPermission = {},
                    onOpenSettings = {},
                    cameraContent = { Text("camera") },
                )
            }
        }

        compose.onNodeWithTag(MainScreenTags.CAMERA).assertIsDisplayed()
    }

    @Test
    fun a_refused_camera_shows_the_way_to_settings() {
        compose.setContent {
            MirrorTheme {
                MainScreen(
                    status = CameraPermissionStatus.Denied,
                    onRequestPermission = {},
                    onOpenSettings = {},
                    cameraContent = {},
                )
            }
        }

        compose.onNodeWithTag(MainScreenTags.PERMISSION_DENIED).assertIsDisplayed()
    }
}
