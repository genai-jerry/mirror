package com.genaijerry.mirror.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.genaijerry.mirror.LanguageCatalogue
import com.genaijerry.mirror.LanguageOption
import com.genaijerry.mirror.LanguagePair
import com.genaijerry.mirror.LanguagePickerState
import com.genaijerry.mirror.LanguagesStatus
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** The picker draws what the backend listed, and nothing of its own. */
@RunWith(AndroidJUnit4::class)
class LanguagePickerSheetTest {

    @get:Rule
    val compose = createComposeRule()

    private val twoSources = LanguageCatalogue(
        sources = listOf(LanguageOption("ml-IN", "Malayalam"), LanguageOption("ta-IN", "Tamil")),
        targets = listOf(LanguageOption("en-IN", "English")),
    )

    private fun sheet(
        state: LanguagePickerState,
        onChoose: (LanguagePair) -> Unit = {},
        onClose: () -> Unit = {},
    ) {
        compose.setContent {
            MirrorTheme { LanguagePickerSheet(state = state, onChoose = onChoose, onClose = onClose) }
        }
    }

    @Test
    fun every_language_the_backend_listed_is_offered() {
        sheet(LanguagePickerState(catalogue = twoSources, status = LanguagesStatus.Loaded))

        compose.onNodeWithTag(LanguagePickerTags.source("ml-IN")).assertIsDisplayed()
        compose.onNodeWithTag(LanguagePickerTags.source("ta-IN")).assertIsDisplayed()
        compose.onNodeWithTag(LanguagePickerTags.target("en-IN")).assertIsDisplayed()
    }

    @Test
    fun choosing_a_source_language_keeps_the_target_as_it_was() {
        var chosen: LanguagePair? = null
        sheet(
            state = LanguagePickerState(catalogue = twoSources, status = LanguagesStatus.Loaded),
            onChoose = { chosen = it },
        )

        compose.onNodeWithTag(LanguagePickerTags.source("ta-IN")).performClick()

        assertEquals(LanguagePair(source = "ta-IN", target = "en-IN"), chosen)
    }

    @Test
    fun the_picker_says_when_the_languages_could_not_be_loaded() {
        sheet(LanguagePickerState(status = LanguagesStatus.Unavailable))

        compose.onNodeWithTag(LanguagePickerTags.UNAVAILABLE).assertIsDisplayed()
    }

    @Test
    fun the_picker_says_while_it_is_still_asking() {
        sheet(LanguagePickerState(status = LanguagesStatus.Loading))

        compose.onNodeWithTag(LanguagePickerTags.LOADING).assertIsDisplayed()
    }

    @Test
    fun closing_the_picker_reports_it() {
        var closed = false
        sheet(
            state = LanguagePickerState(catalogue = twoSources, status = LanguagesStatus.Loaded),
            onClose = { closed = true },
        )

        compose.onNodeWithTag(LanguagePickerTags.CLOSE).performClick()

        assertEquals(true, closed)
    }
}
