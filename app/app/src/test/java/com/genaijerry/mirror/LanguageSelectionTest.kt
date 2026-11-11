package com.genaijerry.mirror

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import java.io.IOException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

/**
 * What the picker offers and what pair is in force.
 *
 * The case this exists for is the one a tester runs by hand (ST-7): an
 * operator adds a language to backend configuration, and it appears in the
 * picker on the next open, with no app update.
 */
@RunWith(AndroidJUnit4::class)
class LanguageSelectionTest {

    @get:Rule
    val folder = TemporaryFolder()

    private val scope = CoroutineScope(Dispatchers.IO + Job())
    private val backend = FakeLanguageCatalogue()

    @After
    fun closeStore() {
        scope.cancel()
    }

    // One store per test, because DataStore allows one reader of a file at a
    // time; two selections over it are the app opening twice.
    private val choices by lazy {
        choiceStore(File(folder.root, "choice.preferences_pb"), scope)
    }

    private fun selection(): LanguageSelection =
        LanguageSelection(catalogues = backend, choices = choices)

    @Test
    fun the_app_opens_on_the_languages_the_backend_lists() = runTest {
        val languages = selection()

        languages.start()

        assertEquals(LanguagesStatus.Loaded, languages.state.status)
        assertEquals(malayalamToEnglish(), languages.state.catalogue)
        assertEquals(LanguagePair.Default, languages.pair)
    }

    @Test
    fun a_language_added_in_backend_configuration_appears_the_next_time_the_picker_opens() =
        runTest {
            val languages = selection()
            languages.start()
            assertEquals(listOf("ml-IN"), languages.state.catalogue.sources.map { it.code })

            // The operator loads the add-Tamil configuration. Nothing about the
            // app changes — it just asks again.
            backend.answer = LanguageCatalogue(
                sources = listOf(
                    LanguageOption("ml-IN", "Malayalam"),
                    LanguageOption("ta-IN", "Tamil"),
                ),
                targets = listOf(LanguageOption("en-IN", "English")),
            )
            languages.refresh()

            assertEquals(listOf("ml-IN", "ta-IN"), languages.state.catalogue.sources.map { it.code })
            assertEquals(2, backend.reads)
        }

    @Test
    fun the_pair_a_person_chose_is_the_pair_the_next_run_starts_on() = runTest {
        val chosen = LanguagePair(source = "ta-IN", target = "en-IN")
        val first = selection()
        first.start()

        first.choose(chosen)
        assertEquals(chosen, first.pair)

        // A second selection over the same file is the app opening again.
        val again = selection()
        again.start()
        assertEquals(chosen, again.pair)
        assertEquals(chosen, choices.chosenPair())
    }

    @Test
    fun a_backend_that_cannot_be_read_says_so_and_offers_nothing() = runTest {
        backend.failure = IOException("no backend here")
        val languages = selection()

        languages.start()

        assertEquals(LanguagesStatus.Unavailable, languages.state.status)
        assertEquals(LanguageCatalogue(), languages.state.catalogue)
    }

    @Test
    fun one_failed_read_does_not_empty_the_list_the_picker_already_had() = runTest {
        val languages = selection()
        languages.start()

        backend.failure = IOException("the backend went away")
        languages.refresh()

        assertEquals(LanguagesStatus.Unavailable, languages.state.status)
        assertEquals(malayalamToEnglish(), languages.state.catalogue)
    }

    @Test
    fun opening_and_closing_the_picker_is_remembered_for_the_screen() {
        val languages = selection()

        languages.open()
        assertTrue(languages.state.isOpen)

        languages.close()
        assertFalse(languages.state.isOpen)
    }
}
