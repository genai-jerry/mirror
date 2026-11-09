package com.genaijerry.mirror

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.core.handlers.ReplaceFileCorruptionHandler
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.first

private val SOURCE = stringPreferencesKey("source_language")
private val TARGET = stringPreferencesKey("target_language")

/**
 * The pair of languages a person last chose, kept on disk.
 *
 * It is written when they choose and read when the app opens, so the choice
 * survives closing the app. Nothing was chosen yet on a new install, and then
 * the pair is Malayalam to English ([LanguagePair.Default]).
 */
class LanguageChoiceStore(private val preferences: DataStore<Preferences>) {

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

/**
 * The file the chosen languages live in. One of these per process, which is
 * all DataStore allows for one file.
 *
 * A file DataStore cannot parse is replaced rather than thrown at the app:
 * forgetting a stored choice costs the default pair, while a read that throws
 * would crash the app on every open until someone cleared its data.
 */
fun languagePreferences(scope: CoroutineScope, produceFile: () -> File): DataStore<Preferences> =
    PreferenceDataStoreFactory.create(
        corruptionHandler = ReplaceFileCorruptionHandler { emptyPreferences() },
        scope = scope,
        produceFile = produceFile,
    )

/** Where the app keeps that file: its own data directory, nowhere shared. */
fun Context.languageChoiceFile(): File =
    File(filesDir, "datastore/language-choice.preferences_pb")
