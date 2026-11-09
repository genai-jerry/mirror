package com.genaijerry.mirror

import androidx.test.ext.junit.runners.AndroidJUnit4
import java.io.IOException
import kotlinx.coroutines.test.runTest
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/**
 * The app's side of `GET /v1/languages`. The backend here is a fake server in
 * this process: no test reaches a real one.
 */
@RunWith(AndroidJUnit4::class)
class BackendLanguageCatalogueTest {

    private val server = MockWebServer()

    @Before
    fun startServer() {
        server.start()
    }

    @After
    fun stopServer() {
        server.close()
    }

    private fun catalogueUnderTest() = BackendLanguageCatalogue(baseUrl = server.url("/").toString())

    @Test
    fun the_app_reads_the_languages_the_backend_lists() = runTest {
        server.enqueue(
            MockResponse.Builder().code(200).body(
                """
                {"sources": [{"code": "ml-IN", "name": "Malayalam"},
                             {"code": "ta-IN", "name": "Tamil"}],
                 "targets": [{"code": "en-IN", "name": "English"}]}
                """.trimIndent(),
            ).build(),
        )

        val read = catalogueUnderTest().catalogue()

        assertEquals(listOf("ml-IN", "ta-IN"), read.sources.map { it.code })
        assertEquals(listOf("Malayalam", "Tamil"), read.sources.map { it.name })
        assertEquals(listOf(LanguageOption("en-IN", "English")), read.targets)
    }

    @Test
    fun the_app_asks_the_languages_endpoint_under_the_base_url() = runTest {
        server.enqueue(MockResponse.Builder().code(200).body("""{"sources": [], "targets": []}""").build())

        catalogueUnderTest().catalogue()

        val asked = server.takeRequest()
        assertEquals("GET", asked.method)
        assertEquals("/v1/languages", asked.target)
    }

    @Test
    fun a_backend_offering_no_languages_yet_gives_empty_lists() = runTest {
        server.enqueue(MockResponse.Builder().code(200).body("{}").build())

        val read = catalogueUnderTest().catalogue()

        assertTrue(read.isEmpty)
    }

    @Test(expected = IOException::class)
    fun a_backend_that_fails_is_not_a_list_of_no_languages() = runTest {
        server.enqueue(MockResponse.Builder().code(500).body("{}").build())

        catalogueUnderTest().catalogue()
    }

    @Test(expected = IOException::class)
    fun an_answer_this_app_cannot_read_is_refused_rather_than_half_used() = runTest {
        server.enqueue(
            MockResponse.Builder().code(200)
                .body("""{"sources": [{"code": "ml-IN"}], "targets": []}""")
                .build(),
        )

        catalogueUnderTest().catalogue()
    }
}
