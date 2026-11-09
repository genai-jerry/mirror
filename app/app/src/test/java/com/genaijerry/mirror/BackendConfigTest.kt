package com.genaijerry.mirror

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
}
