package com.genaijerry.mirror

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.IOException
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The app's side of `POST /v1/frames/translate`. The backend here is a fake
 * server in this process: no test sends a frame to a real one, and no test
 * reaches Sarvam.
 */
@RunWith(AndroidJUnit4::class)
class BackendFrameTranslatorTest {

    private val server = MockWebServer()

    @Before
    fun startServer() {
        server.start()
    }

    @After
    fun stopServer() {
        server.close()
    }

    private fun translatorUnderTest(
        appToken: String = "",
        pair: LanguagePair = LanguagePair.Default,
    ) = BackendFrameTranslator(
        languages = { pair },
        baseUrl = server.url("/").toString(),
        appToken = appToken,
    )

    private fun translated(
        recognized: String = "Kerala in Malayalam",
        translation: String = "Kerala",
        hint: String = """{"x": 0.1, "y": 0.4, "width": 0.8, "height": 0.2}""",
        cached: Boolean = false,
    ) = MockResponse.Builder().code(200).body(
        """
        {"recognized_text": "$recognized", "translated_text": "$translation",
         "region_hint": $hint, "cached": $cached}
        """.trimIndent(),
    ).build()

    @Test
    fun the_crop_and_the_chosen_pair_are_posted_to_the_frame_endpoint() = runTest {
        server.enqueue(translated())

        translatorUnderTest(pair = LanguagePair("ml-IN", "en-IN"))
            .translate(aCropOf(NormalizedRect(0.1f, 0.4f, 0.8f, 0.2f)))

        val asked = server.takeRequest()
        assertEquals("POST", asked.method)
        assertEquals("/v1/frames/translate", asked.target)
        assertTrue(asked.headers["Content-Type"]!!.startsWith("multipart/form-data"))
        val sent = asked.body!!.utf8()
        assertTrue("the image part is missing", sent.contains("""name="image""""))
        assertTrue("the image is not sent as a JPEG", sent.contains("image/jpeg"))
        assertTrue(sent.contains("""name="source_language""""))
        assertTrue(sent.contains("ml-IN"))
        assertTrue(sent.contains("""name="target_language""""))
        assertTrue(sent.contains("en-IN"))
    }

    @Test
    fun the_pair_is_read_at_the_moment_of_the_call_not_when_the_app_started() = runTest {
        var pair = LanguagePair("ml-IN", "en-IN")
        val translator = BackendFrameTranslator(
            languages = { pair },
            baseUrl = server.url("/").toString(),
            appToken = "",
        )
        server.enqueue(translated())
        server.enqueue(translated())

        translator.translate(aCropOf(NormalizedRect.CENTRE))
        server.takeRequest()
        pair = LanguagePair("ta-IN", "en-IN")
        translator.translate(aCropOf(NormalizedRect.CENTRE))

        assertTrue(server.takeRequest().body!!.utf8().contains("ta-IN"))
    }

    @Test
    fun the_request_carries_the_app_token_this_build_was_given() = runTest {
        server.enqueue(translated())

        translatorUnderTest(appToken = "the-app-token").translate(aCropOf(NormalizedRect.CENTRE))

        assertEquals("Bearer the-app-token", server.takeRequest().headers["Authorization"])
    }

    @Test
    fun a_build_with_no_app_token_sends_no_authorization_at_all() = runTest {
        server.enqueue(translated())

        translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))

        assertNull(server.takeRequest().headers["Authorization"])
    }

    @Test
    fun the_text_the_translation_and_where_it_was_read_all_come_back() = runTest {
        server.enqueue(translated(cached = true))

        val answer = translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))

        assertEquals("Kerala in Malayalam", answer.recognizedText)
        assertEquals("Kerala", answer.translatedText)
        assertRect(NormalizedRect(0.1f, 0.4f, 0.8f, 0.2f), answer.regionHint)
        assertTrue(answer.cached)
        assertFalse(answer.isBlank)
    }

    @Test
    fun a_crop_with_no_text_in_it_comes_back_as_an_answer_with_nothing_in_it() = runTest {
        server.enqueue(translated(recognized = "", translation = "", hint = "null"))

        val answer = translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))

        assertTrue(answer.isBlank)
        assertNull(answer.regionHint)
    }

    @Test(expected = IOException::class)
    fun a_backend_out_of_recognition_allowance_is_a_failed_cycle() = runTest {
        // 429 budget_exhausted, the one the shared allowance answers with.
        server.enqueue(
            MockResponse.Builder().code(429)
                .body("""{"error": {"code": "budget_exhausted", "message": "Try later."}}""")
                .build(),
        )

        translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))
    }

    @Test(expected = IOException::class)
    fun a_recognition_that_timed_out_is_a_failed_cycle() = runTest {
        server.enqueue(
            MockResponse.Builder().code(504)
                .body("""{"error": {"code": "recognition_timeout", "message": "Too slow."}}""")
                .build(),
        )

        translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))
    }

    @Test(expected = IOException::class)
    fun a_language_pair_the_backend_does_not_offer_is_a_failed_cycle() = runTest {
        server.enqueue(
            MockResponse.Builder().code(400)
                .body("""{"error": {"code": "unsupported_language", "message": "No fr-FR."}}""")
                .build(),
        )

        translatorUnderTest(pair = LanguagePair("fr-FR", "en-IN"))
            .translate(aCropOf(NormalizedRect.CENTRE))
    }

    @Test(expected = IOException::class)
    fun an_answer_missing_its_translation_is_refused_rather_than_read_as_a_blank_wall() = runTest {
        // Were this read as "no text", it would wipe a good overlay off the
        // screen on the strength of an answer the app cannot understand.
        server.enqueue(
            MockResponse.Builder().code(200)
                .body("""{"recognized_text": "Kerala in Malayalam"}""")
                .build(),
        )

        translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))
    }

    @Test(expected = IOException::class)
    fun an_answer_that_is_not_json_at_all_is_a_failed_cycle() = runTest {
        server.enqueue(MockResponse.Builder().code(200).body("<html>a proxy page</html>").build())

        translatorUnderTest().translate(aCropOf(NormalizedRect.CENTRE))
    }
}
