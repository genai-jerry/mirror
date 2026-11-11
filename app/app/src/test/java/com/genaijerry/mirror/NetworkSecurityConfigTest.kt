package com.genaijerry.mirror

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element

/**
 * The app's plain-HTTP rules (epic 61, design decision D12). Gradle runs unit
 * tests in the module's folder, app/app, so the files are read by relative
 * path.
 */
class NetworkSecurityConfigTest {

    private val stagingTemplate = File("network-security/staging.xml")
    private val mainConfig = File("src/main/res/xml/network_security_config.xml")
    private val stagingManifest = File("src/staging/AndroidManifest.xml")
    private val buildFile = File("build.gradle.kts")

    @Test
    fun the_staging_rule_refuses_plain_http_by_default() {
        assertEquals("false", baseConfig(stagingTemplate).getAttribute("cleartextTrafficPermitted"))
    }

    @Test
    fun the_staging_rule_allows_plain_http_to_the_staging_host_and_no_other() {
        val rules = cleartextDomainConfigs(stagingTemplate)
        assertEquals(1, rules.size)
        val domains = rules.single().children("domain")
        assertEquals(1, domains.size)
        assertEquals(STAGING_HOST_PLACEHOLDER, domains.single().textContent.trim())
        assertEquals("false", domains.single().getAttribute("includeSubdomains"))
    }

    @Test
    fun the_build_fills_the_same_placeholder_the_staging_rule_holds() {
        assertTrue(buildFile.readText().contains("\"$STAGING_HOST_PLACEHOLDER\""))
    }

    @Test
    fun the_staging_build_reads_the_generated_rule() {
        val text = stagingManifest.readText()
        assertTrue(text.contains("android:networkSecurityConfig=\"@xml/network_security_config_staging\""))
        assertTrue(text.contains("tools:replace=\"android:networkSecurityConfig\""))
    }

    @Test
    fun the_dev_and_system_test_rule_refuses_plain_http_by_default() {
        assertEquals("false", baseConfig(mainConfig).getAttribute("cleartextTrafficPermitted"))
    }

    @Test
    fun the_dev_and_system_test_rule_allows_exactly_the_local_addresses() {
        val domains = cleartextDomainConfigs(mainConfig).flatMap { it.children("domain") }
        assertEquals(
            setOf("127.0.0.1", "localhost", "10.0.2.2"),
            domains.map { it.textContent.trim() }.toSet(),
        )
        assertEquals(3, domains.size)
        assertTrue(domains.all { it.getAttribute("includeSubdomains") == "false" })
    }

    private fun root(file: File): Element =
        DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file).documentElement

    private fun baseConfig(file: File): Element = root(file).children("base-config").single()

    private fun cleartextDomainConfigs(file: File): List<Element> =
        root(file).children("domain-config")
            .filter { it.getAttribute("cleartextTrafficPermitted") == "true" }

    private fun Element.children(name: String): List<Element> =
        (0 until childNodes.length).map { childNodes.item(it) }
            .filterIsInstance<Element>()
            .filter { it.tagName == name }

    private companion object {
        /** The build file replaces this with the staging backend's host. */
        const val STAGING_HOST_PLACEHOLDER = "@STAGING_HOST@"
    }
}
