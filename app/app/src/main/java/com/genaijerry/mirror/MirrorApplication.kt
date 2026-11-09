package com.genaijerry.mirror

import android.app.Application
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * Where the app's long-lived pieces are built.
 *
 * The chosen language pair and the list of languages outlive the one screen,
 * so they are held here rather than in the activity. Holding them in one
 * place is also what lets a unit test put a fake backend in: the test runs
 * against its own application, and nothing in a test reaches a real backend.
 */
open class MirrorApplication : Application() {

    /** As long-lived as the app: what the preferences file is read and written on. */
    private val fileScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    /** The languages this session translates between, and what the picker offers. */
    open val languages: LanguageSelection by lazy {
        LanguageSelection(
            catalogues = BackendLanguageCatalogue(),
            choices = LanguageChoiceStore(
                languagePreferences(fileScope) { languageChoiceFile() },
            ),
        )
    }
}
