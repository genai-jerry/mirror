package com.genaijerry.mirror

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first

private val SOURCE = stringPreferencesKey("source_language")
private val TARGET = stringPreferencesKey("target_language")

/** The app's own file of chosen languages. One per process, as DataStore requires. */
private val Context.languageChoices: DataStore<Preferences> by
    preferencesDataStore(name = "language-choice")

/**
 * The pair of languages a person last chose, kept on disk.
 *
 * It is written when they choose and read when the app opens, so the choice
 * survives closing the app. Nothing was chosen yet on a new install, and then
 * the pair is Malayalam to English ([LanguagePair.Default]).
 */
class LanguageChoiceStore(private val preferences: DataStore<Preferences>) {

    constructor(context: Context) : this(context.applicationContext.languageChoices)

    /** The pair in force, or the default when nothing has been chosen yet. */
    suspend fun chosenPair(): LanguagePair {
        val stored = preferences.data.first()
        val source = stored[SOURCE]
        val target = stored[TARGET]
        return if (source.isNullOrBlank() || target.isNullOrBlank()) {
            LanguagePair.Default
        } else {
            LanguagePair(source = source, target = target)
        }
    }

    /** Remember this pair for the next time the app opens. */
    suspend fun remember(pair: LanguagePair) {
        preferences.edit { stored ->
            stored[SOURCE] = pair.source
            stored[TARGET] = pair.target
        }
    }
}
