package com.genaijerry.mirror

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.job
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith

/** The chosen pair of languages is written to disk, so it outlives one run. */
@RunWith(AndroidJUnit4::class)
class LanguageChoiceStoreTest {

    @get:Rule
    val folder = TemporaryFolder()

    private fun choiceFile() = File(folder.root, "language-choice.preferences_pb")

    @Test
    fun a_new_install_starts_on_malayalam_to_english() = runTest {
        val scope = CoroutineScope(Dispatchers.IO + Job())

        val pair = choiceStore(choiceFile(), scope).chosenPair()

        assertEquals(LanguagePair.Default, pair)
        assertEquals(LanguagePair("ml-IN", "en-IN"), pair)
        scope.cancel()
    }

    @Test
    fun the_chosen_pair_is_still_there_the_next_time_the_app_opens() = runTest {
        val file = choiceFile()
        val chosen = LanguagePair(source = "ta-IN", target = "en-IN")

        val firstRun = CoroutineScope(Dispatchers.IO + Job())
        choiceStore(file, firstRun).remember(chosen)
        // The app closes: this store is done with the file.
        firstRun.cancel()
        firstRun.coroutineContext.job.join()

        val nextRun = CoroutineScope(Dispatchers.IO + Job())
        val restored = choiceStore(file, nextRun).chosenPair()
        nextRun.cancel()

        assertEquals(chosen, restored)
    }
}
