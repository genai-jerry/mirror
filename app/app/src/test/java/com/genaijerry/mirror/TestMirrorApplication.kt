package com.genaijerry.mirror

import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job

/**
 * The application the activity tests run against.
 *
 * It is the real one with the backend taken out: the list of languages comes
 * from [catalogues], a frame to translate goes to [translations], and the
 * chosen pair is a file in this test's own cache — so an activity test reaches
 * no backend and leaves nothing behind.
 */
class TestMirrorApplication : MirrorApplication() {

    val catalogues = FakeLanguageCatalogue()

    val translations = FakeFrameTranslator()

    override val frames: FrameTranslator get() = translations

    private val scope = CoroutineScope(Dispatchers.IO + Job())

    override val languages: LanguageSelection by lazy {
        LanguageSelection(
            catalogues = catalogues,
            choices = choiceStore(File(cacheDir, "test-choice.preferences_pb"), scope),
        )
    }
}
