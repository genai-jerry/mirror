package com.genaijerry.mirror

import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.io.IOException

private const val TAG = "LanguageSelection"

/** Whether the app has the list of languages the picker needs. */
enum class LanguagesStatus {
    /** Asking the backend for the list. */
    Loading,

    /** The list came back and is what the picker shows. */
    Loaded,

    /** The backend could not be read. The list, if there is one, is the last we read. */
    Unavailable,
}

/** Everything the language picker draws, and the pair in force. */
data class LanguagePickerState(
    val pair: LanguagePair = LanguagePair.Default,
    val catalogue: LanguageCatalogue = LanguageCatalogue(),
    val status: LanguagesStatus = LanguagesStatus.Loading,
    val isOpen: Boolean = false,
)

/**
 * The languages this session uses: which pair is in force, and what the
 * picker offers.
 *
 * The list is read from the backend when the app opens and again every time
 * the picker opens, and is not kept anywhere in between (design decision D6).
 * That is what makes a language an operator adds to backend configuration
 * appear in the picker on the next open, with no app update.
 *
 * The chosen pair is the other way round: it is written to disk, so it
 * survives closing the app, and it is what every frame translation request
 * sends as its source and target language.
 */
class LanguageSelection(
    private val catalogues: LanguageCatalogueSource,
    private val choices: LanguageChoiceStore,
) {

    var state: LanguagePickerState by mutableStateOf(LanguagePickerState())
        private set

    /** The pair every frame translation request is made with. */
    val pair: LanguagePair get() = state.pair

    /** What the app does on the way in: restore the choice, then read the list. */
    suspend fun start() {
        state = state.copy(pair = choices.chosenPair())
        refresh()
    }

    /** Read the list of languages again. The picker does this every time it opens. */
    suspend fun refresh() {
        state = state.copy(status = LanguagesStatus.Loading)
        state = try {
            state.copy(catalogue = catalogues.catalogue(), status = LanguagesStatus.Loaded)
        } catch (failure: IOException) {
            // Keep the list last read. A picker that empties itself because one
            // call failed is worse than one showing a list a minute old, and
            // the next open asks again anyway.
            Log.w(TAG, "The list of languages could not be read", failure)
            state.copy(status = LanguagesStatus.Unavailable)
        }
    }

    /** Use this pair from now on, and remember it for the next time the app opens. */
    suspend fun choose(pair: LanguagePair) {
        state = state.copy(pair = pair)
        choices.remember(pair)
    }

    fun open() {
        state = state.copy(isOpen = true)
    }

    fun close() {
        state = state.copy(isOpen = false)
    }
}
