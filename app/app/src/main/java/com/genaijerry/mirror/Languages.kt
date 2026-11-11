package com.genaijerry.mirror

/**
 * The languages this app may read and translate into, and the pair a person
 * has chosen.
 *
 * None of it is written into the app: the backend's `GET /v1/languages`
 * answers from configuration (design decision D6), so a language an operator
 * adds appears in the picker with no app release. The only thing fixed here is
 * which pair a brand-new install starts on.
 */

/** One language the picker offers: the code the backend uses, and its name. */
data class LanguageOption(val code: String, val name: String)

/** Everything the picker offers right now, exactly as the backend listed it. */
data class LanguageCatalogue(
    val sources: List<LanguageOption> = emptyList(),
    val targets: List<LanguageOption> = emptyList(),
) {
    /** The name the backend gave this code, or the code itself when it is not offered. */
    fun nameOf(code: String): String =
        (sources + targets).firstOrNull { it.code.equals(code, ignoreCase = true) }?.name ?: code

    val isEmpty: Boolean get() = sources.isEmpty() && targets.isEmpty()
}

/** The pair of languages this session translates between. */
data class LanguagePair(val source: String, val target: String) {
    companion object {
        /** Malayalam to English — what a new install starts on, as the design says. */
        val Default = LanguagePair(source = "ml-IN", target = "en-IN")
    }
}

/** Where the list of languages comes from. The app has one; the tests fake it. */
fun interface LanguageCatalogueSource {
    /** The languages offered right now. Throws when the backend cannot be read. */
    suspend fun catalogue(): LanguageCatalogue
}
