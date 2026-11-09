package com.genaijerry.mirror

import java.io.File
import java.io.IOException
import kotlinx.coroutines.CoroutineScope

/** What the tests use instead of a backend. No test reads the real one. */
class FakeLanguageCatalogue(
    var answer: LanguageCatalogue = malayalamToEnglish(),
    var failure: IOException? = null,
) : LanguageCatalogueSource {

    /** How many times the app has asked. The picker asks on every open. */
    var reads: Int = 0
        private set

    override suspend fun catalogue(): LanguageCatalogue {
        reads++
        failure?.let { throw it }
        return answer
    }
}

/** The shipped configuration: Malayalam read, English written. */
fun malayalamToEnglish() = LanguageCatalogue(
    sources = listOf(LanguageOption("ml-IN", "Malayalam")),
    targets = listOf(LanguageOption("en-IN", "English")),
)

/**
 * A store of chosen languages in a file of this test's own, built the way the
 * app builds its own — so what the tests prove is what the app does.
 */
fun choiceStore(file: File, scope: CoroutineScope): LanguageChoiceStore =
    LanguageChoiceStore(languagePreferences(scope) { file })
