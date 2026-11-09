package com.genaijerry.mirror.ui

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.genaijerry.mirror.LanguageCatalogue
import com.genaijerry.mirror.LanguageOption
import com.genaijerry.mirror.LanguagePair
import com.genaijerry.mirror.LanguagePickerState
import com.genaijerry.mirror.LanguagesStatus
import com.genaijerry.mirror.NormalizedRect
import com.genaijerry.mirror.TranslatedOverlay
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class MainScreenTest {

    @get:Rule
    val compose = createComposeRule()

    private val loaded = LanguagePickerState(
        catalogue = LanguageCatalogue(
            sources = listOf(LanguageOption("ml-IN", "Malayalam")),
            targets = listOf(LanguageOption("en-IN", "English")),
        ),
        status = LanguagesStatus.Loaded,
    )

    private fun screen(
        status: CameraPermissionStatus,
        languages: LanguagePickerState = loaded,
        onRequestPermission: () -> Unit = {},
        onOpenSettings: () -> Unit = {},
        onOpenPicker: () -> Unit = {},
        onClosePicker: () -> Unit = {},
        onChooseLanguages: (LanguagePair) -> Unit = {},
        overlay: TranslatedOverlay? = null,
        cameraContent: @Composable () -> Unit = {},
    ) {
        compose.setContent {
            MirrorTheme {
                MainScreen(
                    status = status,
                    onRequestPermission = onRequestPermission,
                    onOpenSettings = onOpenSettings,
                    languages = languages,
                    onOpenPicker = onOpenPicker,
                    onClosePicker = onClosePicker,
                    onChooseLanguages = onChooseLanguages,
                    overlay = overlay,
                    cameraContent = cameraContent,
                )
            }
        }
    }

    @Test
    fun the_screen_asks_for_the_camera_exactly_once_when_it_opens() {
        var asked = 0

        screen(status = CameraPermissionStatus.NotAsked, onRequestPermission = { asked++ })
        compose.waitForIdle()

        assertEquals(1, asked)
        compose.onNodeWithTag(MainScreenTags.STARTING).assertIsDisplayed()
    }

    @Test
    fun the_camera_view_fills_the_screen_once_the_camera_is_allowed() {
        screen(status = CameraPermissionStatus.Granted, cameraContent = { Text("camera") })

        compose.onNodeWithTag(MainScreenTags.CAMERA).assertIsDisplayed()
    }

    @Test
    fun a_refused_camera_shows_the_way_to_settings() {
        screen(status = CameraPermissionStatus.Denied)

        compose.onNodeWithTag(MainScreenTags.PERMISSION_DENIED).assertIsDisplayed()
    }

    @Test
    fun the_screen_names_the_pair_in_force() {
        screen(status = CameraPermissionStatus.Granted)

        compose.onNodeWithText("Malayalam → English").assertIsDisplayed()
    }

    @Test
    fun the_picker_is_reachable_while_the_camera_is_running() {
        var opened = 0

        screen(status = CameraPermissionStatus.Granted, onOpenPicker = { opened++ })
        compose.onNodeWithTag(LanguagePickerTags.OPEN).performClick()

        assertEquals(1, opened)
    }

    @Test
    fun the_picker_is_not_drawn_until_it_is_opened() {
        screen(status = CameraPermissionStatus.Granted)

        compose.onNodeWithTag(LanguagePickerTags.SHEET).assertDoesNotExist()
    }

    @Test
    fun an_open_picker_is_drawn_over_the_camera() {
        screen(status = CameraPermissionStatus.Granted, languages = loaded.copy(isOpen = true))

        compose.onNodeWithTag(LanguagePickerTags.SHEET).assertIsDisplayed()
    }

    @Test
    fun the_translation_is_drawn_over_the_camera() {
        screen(
            status = CameraPermissionStatus.Granted,
            overlay = TranslatedOverlay(text = "Kerala", region = SOME_TEXT),
            cameraContent = { Text("camera") },
        )

        compose.onNodeWithText("Kerala").assertIsDisplayed()
    }

    @Test
    fun no_translation_is_drawn_while_the_camera_is_still_being_asked_for() {
        screen(
            status = CameraPermissionStatus.NotAsked,
            overlay = TranslatedOverlay(text = "Kerala", region = SOME_TEXT),
        )

        compose.onNodeWithTag(TranslatedOverlayTags.TEXT).assertDoesNotExist()
    }

    private companion object {
        val SOME_TEXT = NormalizedRect(x = 0.1f, y = 0.4f, width = 0.8f, height = 0.1f)
    }
}
