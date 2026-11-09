package com.genaijerry.mirror

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class BackendConfigTest {

    @Test
    fun the_build_names_a_backend() {
        assertTrue(
            "The build flavour must set BACKEND_BASE_URL",
            BackendConfig.baseUrl.startsWith("http"),
        )
    }

    @Test
    fun the_backend_url_ends_with_a_slash_so_paths_append_cleanly() {
        assertTrue(BackendConfig.baseUrl.endsWith("/"))
    }

    @Test
    fun the_build_carries_an_app_token_field_the_app_can_read() {
        // The dev flavour sets no token, which is the backend's own default:
        // the switch of design decision D10 is off on both sides.
        assertEquals("", BackendConfig.appToken)
        assertFalse(BackendConfig.sendsAppToken)
    }
}
