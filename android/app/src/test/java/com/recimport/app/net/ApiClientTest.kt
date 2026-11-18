package com.recimport.app.net

import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okio.Buffer
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class ApiClientTest {
    private lateinit var server: MockWebServer
    private lateinit var client: ApiClient
    private lateinit var base: String

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        base = server.url("/").toString().trimEnd('/')
        client = ApiClient()
    }

    @After
    fun tearDown() {
        try {
            server.shutdown()
        } catch (e: Exception) {
        }
    }

    private fun settings(gemini: String = "") = Settings(base, "secret-token", gemini)

    @Test
    fun wakeSucceedsAfterOneFailure() {
        server.enqueue(MockResponse().setResponseCode(503))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"ok\":true}"))
        assertTrue(client.wake(base, attempts = 3, delayMs = 10))
        assertEquals(2, server.requestCount)
        val r = server.takeRequest()
        assertEquals("/health", r.path)
        assertNull(r.getHeader("Authorization"))
    }

    @Test
    fun wakeFalseWhenAlways503() {
        for (i in 0 until 3) server.enqueue(MockResponse().setResponseCode(503))
        assertFalse(client.wake(base, attempts = 3, delayMs = 10))
        assertEquals(3, server.requestCount)
    }

    @Test
    fun createJobSendsExpectedRequest() {
        server.enqueue(MockResponse().setResponseCode(202).setBody("{\"id\":\"abc123\"}"))
        val id = client.createJob(settings(), "Pasta \"quoted\"\nline")
        assertEquals("abc123", id)
        val r = server.takeRequest()
        assertEquals("POST", r.method)
        assertEquals("/v1/jobs", r.path)
        assertEquals("Bearer secret-token", r.getHeader("Authorization"))
        assertNull(r.getHeader("X-Gemini-Key"))
        assertEquals("Pasta \"quoted\"\nline", JSONObject(r.body.readUtf8()).getString("text"))
    }

    @Test
    fun createJobSendsGeminiKeyWhenSet() {
        server.enqueue(MockResponse().setResponseCode(202).setBody("{\"id\":\"x\"}"))
        client.createJob(settings("gem-key"), "hi")
        val r = server.takeRequest()
        assertEquals("gem-key", r.getHeader("X-Gemini-Key"))
    }

    @Test
    fun getJobParsesDoneWithRecipe() {
        val body = """{"id":"j1","status":"done","title":"Pasta Bake","source":"text",
            "recipe":{"title":"Pasta Bake","description":"d","preparationTime":"10 min",
            "cookingTime":"20 min","totalTime":30,"quantity":"4","category":"Main",
            "cookware":["pan"],"ingredients":["pasta","cheese"],"instructions":["boil","bake"]}}"""
        server.enqueue(MockResponse().setResponseCode(200).setBody(body))
        val st = client.getJob(settings(), "j1")
        val r = server.takeRequest()
        assertEquals("/v1/jobs/j1", r.path)
        assertEquals("Bearer secret-token", r.getHeader("Authorization"))
        assertEquals(JobStatusKind.DONE, st.kind)
        assertEquals("j1", st.id)
        val rec = st.recipe
        assertNotNull(rec)
        assertEquals(30, rec!!.totalTime)
        assertEquals(listOf("pasta", "cheese"), rec.ingredients)
        assertEquals(listOf("pan"), rec.cookware)
        assertEquals(listOf("boil", "bake"), rec.instructions)
    }

    @Test
    fun getJobParsesError() {
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"id\":\"j2\",\"status\":\"error\",\"error\":\"boom\"}"))
        val st = client.getJob(settings(), "j2")
        assertEquals(JobStatusKind.ERROR, st.kind)
        assertEquals("boom", st.error)
        assertNull(st.recipe)
    }

    @Test
    fun unauthorizedMapsToInvalidToken() {
        server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"Bad token secret-token\"}"))
        try {
            client.getJob(settings(), "j1")
            fail("expected exception")
        } catch (e: ApiException) {
            assertEquals(401, e.code)
            assertEquals("Invalid app token", e.message)
        }
    }

    @Test
    fun validationListDetailIsJoined() {
        server.enqueue(
            MockResponse().setResponseCode(422).setBody(
                "{\"detail\":[{\"loc\":[\"body\",\"text\"],\"msg\":\"field required\",\"type\":\"missing\"}]}"
            )
        )
        try {
            client.createJob(settings(), "x")
            fail("expected exception")
        } catch (e: ApiException) {
            assertEquals(422, e.code)
            assertTrue(e.message!!.contains("field required"))
        }
    }

    @Test
    fun stringDetailAndGenericMessage() {
        server.enqueue(MockResponse().setResponseCode(400).setBody("{\"detail\":\"Too long\"}"))
        server.enqueue(MockResponse().setResponseCode(500).setBody("oops"))
        try {
            client.createJob(settings(), "x")
            fail()
        } catch (e: ApiException) {
            assertEquals("Too long", e.message)
        }
        try {
            client.createJob(settings(), "x")
            fail()
        } catch (e: ApiException) {
            assertEquals(500, e.code)
            assertEquals("HTTP 500", e.message)
        }
    }

    @Test
    fun downloadRtkReturnsBytesAndFilename() {
        val bytes = byteArrayOf(1, 2, 3, 0, 127, -1)
        server.enqueue(
            MockResponse().setResponseCode(200)
                .setHeader("Content-Disposition", "attachment; filename=\"Pasta_Bake.rtk\"")
                .setBody(Buffer().write(bytes))
        )
        val f = client.downloadRtk(settings(), "j1")
        assertEquals("/v1/jobs/j1/rtk", server.takeRequest().path)
        assertEquals("Pasta_Bake.rtk", f.filename)
        assertArrayEquals(bytes, f.bytes)
    }

    @Test
    fun networkFailureIsCodeZero() {
        val s = settings()
        server.shutdown()
        try {
            client.getJob(s, "j1")
            fail("expected exception")
        } catch (e: ApiException) {
            assertEquals(0, e.code)
            assertTrue(e.message!!.startsWith("Network error: "))
            assertFalse(e.message!!.contains("secret-token"))
        }
    }

    @Test
    fun normalizeBaseUrlTable() {
        assertEquals("https://a.example.com", ApiClient.normalizeBaseUrl("  a.example.com/ "))
        assertEquals("https://a.example.com/api", ApiClient.normalizeBaseUrl("https://a.example.com/api//"))
        assertEquals("http://localhost:8000", ApiClient.normalizeBaseUrl("http://localhost:8000/"))
        assertEquals("http://127.0.0.1:8000", ApiClient.normalizeBaseUrl("http://127.0.0.1:8000"))
        assertEquals("http://10.0.2.2:8000", ApiClient.normalizeBaseUrl("http://10.0.2.2:8000"))
        try {
            ApiClient.normalizeBaseUrl("http://example.com")
            fail()
        } catch (e: IllegalArgumentException) {
            assertEquals("Use an https:// URL", e.message)
        }
        for (blank in listOf("", "   ")) {
            try {
                ApiClient.normalizeBaseUrl(blank)
                fail()
            } catch (e: IllegalArgumentException) {
                assertEquals("Backend URL is empty", e.message)
            }
        }
    }

    @Test
    fun parseFilenameTable() {
        assertEquals("Pasta_Bake.rtk", ApiClient.parseFilename("attachment; filename=\"Pasta_Bake.rtk\""))
        assertEquals("Pasta_Bake.rtk", ApiClient.parseFilename("attachment; filename=Pasta_Bake.rtk"))
        assertEquals("Pasta_Bake.rtk", ApiClient.parseFilename("attachment; filename=\"Pasta Bake.rtk\""))
        assertEquals("Soup.rtk", ApiClient.parseFilename("attachment; filename=\"Soup\""))
        assertEquals("b_.rtk", ApiClient.parseFilename("attachment; filename=\"a/b?.rtk\""))
        assertEquals("recipe.rtk", ApiClient.parseFilename(null))
        assertEquals("recipe.rtk", ApiClient.parseFilename("attachment"))
    }

    @Test
    fun parseJobStatusHandlesNullsAndStringTotalTime() {
        val st = ApiClient.parseJobStatus(
            """{"id":"j","status":"DONE","error":null,"title":null,"source":null,
               "recipe":{"title":"T","totalTime":"45","description":null,"ingredients":null}}"""
        )
        assertEquals(JobStatusKind.DONE, st.kind)
        assertNull(st.error)
        assertNull(st.title)
        assertNull(st.source)
        val r = st.recipe!!
        assertEquals(45, r.totalTime)
        assertEquals("", r.description)
        assertEquals(emptyList<String>(), r.ingredients)
        assertEquals("", r.quantity)
    }

    @Test
    fun parseJobStatusQueuedWithoutRecipe() {
        val st = ApiClient.parseJobStatus("{\"id\":\"q\",\"status\":\"Queued\",\"recipe\":null}")
        assertEquals(JobStatusKind.QUEUED, st.kind)
        assertNull(st.recipe)
        assertEquals(JobStatusKind.RUNNING, ApiClient.parseJobStatus("{\"id\":\"q\",\"status\":\"running\"}").kind)
    }
}
