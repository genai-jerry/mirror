package com.genaijerry.mirror

import android.Manifest
import android.app.Application
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.genaijerry.mirror.ui.LanguagePickerTags
import com.genaijerry.mirror.ui.MainScreenTags
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

/**
 * The activity owns the camera permission state and reaches the languages the
 * app holds; MainScreenTest covers what each state draws. This covers who sets
 * it — in particular the check on the way in, which is what makes allowing the
 * camera in Settings take effect when a person comes back to the app.
 */
@RunWith(AndroidJUnit4::class)
@Config(application = TestMirrorApplication::class)
class MainActivityTest {

    @get:Rule
    val compose = createAndroidComposeRule<MainActivity>()

    private val app: TestMirrorApplication
        get() = ApplicationProvider.getApplicationContext()

    @Test
    fun allowing_the_camera_in_settings_takes_effect_when_the_person_comes_back() {
        // The camera is not allowed yet, so the screen is still starting up.
        compose.onNodeWithTag(MainScreenTags.STARTING).assertIsDisplayed()

        // The person allows the camera in Settings while the app is away...
        shadowOf(ApplicationProvider.getApplicationContext<Application>())
            .grantPermissions(Manifest.permission.CAMERA)

        // ...and comes back to it.
        compose.activityRule.scenario.moveToState(Lifecycle.State.CREATED)
        compose.activityRule.scenario.moveToState(Lifecycle.State.RESUMED)
        compose.waitForIdle()

        compose.onNodeWithTag(MainScreenTags.CAMERA).assertIsDisplayed()
    }

    @Test
    fun the_languages_are_read_from_the_backend_when_the_app_opens() {
        compose.waitUntil(WAIT_MILLIS) { app.catalogues.reads >= 1 }

        compose.onNodeWithText("Malayalam → English").assertIsDisplayed()
    }

    @Test
    fun opening_the_picker_asks_the_backend_again() {
        compose.waitUntil(WAIT_MILLIS) { app.catalogues.reads >= 1 }
        val readsAtStart = app.catalogues.reads

        compose.onNodeWithTag(LanguagePickerTags.OPEN).performClick()

        compose.onNodeWithTag(LanguagePickerTags.SHEET).assertIsDisplayed()
        compose.waitUntil(WAIT_MILLIS) { app.catalogues.reads > readsAtStart }
    }

    private companion object {
        /** Reading the languages is a background call, so the tests wait for it. */
        const val WAIT_MILLIS = 5_000L
    }
}
