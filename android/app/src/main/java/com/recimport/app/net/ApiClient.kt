package com.recimport.app.net

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiClient(private val http: OkHttpClient = defaultClient()) {

    fun wake(baseUrl: String, attempts: Int = 12, delayMs: Long = 5000): Boolean {
        val client = http.newBuilder().callTimeout(20, TimeUnit.SECONDS).build()
        val url = baseUrl.trimEnd('/') + "/health"
        for (i in 0 until attempts) {
            try {
                val req = Request.Builder().url(url).get().build()
                client.newCall(req).execute().use { resp ->
                    if (resp.code == 200) {
                        val body = resp.body?.string().orEmpty()
                        val ok = try {
                            JSONObject(body).optBoolean("ok", false)
                        } catch (e: Exception) {
                            false
                        }
                        if (ok) return true
                    }
                }
            } catch (e: IOException) {
                // retry
            } catch (e: IllegalArgumentException) {
                return false
            }
            if (i < attempts - 1) {
                try {
                    Thread.sleep(delayMs)
                } catch (e: InterruptedException) {
                    Thread.currentThread().interrupt()
                    return false
                }
            }
        }
        return false
    }

    fun createJob(s: Settings, text: String): String {
        val body = JSONObject().put("text", text).toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType())
        val req = authed(s, "/v1/jobs").post(body).build()
        return exec(req) { resp ->
            val str = resp.body?.string().orEmpty()
            try {
                JSONObject(str).getString("id")
            } catch (e: Exception) {
                throw ApiException(resp.code, "Unexpected server response")
            }
        }
    }

    fun getJob(s: Settings, id: String): JobStatus {
        val req = authed(s, "/v1/jobs/$id").get().build()
        return exec(req) { resp ->
            val str = resp.body?.string().orEmpty()
            try {
                parseJobStatus(str)
            } catch (e: Exception) {
                throw ApiException(resp.code, "Unexpected server response")
            }
        }
    }

    fun downloadRtk(s: Settings, id: String): RtkFile {
        val req = authed(s, "/v1/jobs/$id/rtk").get().build()
        return exec(req) { resp ->
            val name = parseFilename(resp.header("Content-Disposition"))
            val bytes = resp.body?.bytes() ?: ByteArray(0)
            RtkFile(name, bytes)
        }
    }

    private fun authed(s: Settings, path: String): Request.Builder {
        val b = Request.Builder()
            .url(s.baseUrl.trimEnd('/') + path)
            .header("Authorization", "Bearer " + s.token)
        if (s.geminiKey.isNotBlank()) b.header("X-Gemini-Key", s.geminiKey)
        return b
    }

    private fun <T> exec(req: Request, block: (Response) -> T): T {
        try {
            http.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) throw toException(resp)
                return block(resp)
            }
        } catch (e: IOException) {
            throw ApiException(0, "Network error: " + e.message)
        }
    }

    private fun toException(resp: Response): ApiException {
        val code = resp.code
        if (code == 401) return ApiException(401, "Invalid app token")
        val text = try {
            resp.body?.string().orEmpty()
        } catch (e: IOException) {
            ""
        }
        var msg: String? = null
        try {
            val o = JSONObject(text)
            if (o.has("detail") && !o.isNull("detail")) {
                val d = o.get("detail")
                msg = if (d is JSONArray) {
                    val parts = ArrayList<String>()
                    for (i in 0 until d.length()) {
                        val item = d.opt(i)
                        if (item is JSONObject) {
                            val m = if (item.isNull("msg")) item.toString() else item.optString("msg")
                            val loc = item.optJSONArray("loc")
                            if (loc != null && loc.length() > 0) {
                                val last = loc.opt(loc.length() - 1)
                                parts.add("$last: $m")
                            } else {
                                parts.add(m)
                            }
                        } else {
                            parts.add(item.toString())
                        }
                    }
                    parts.joinToString("; ")
                } else {
                    d.toString()
                }
            }
        } catch (e: Exception) {
            msg = null
        }
        if (msg.isNullOrBlank()) msg = "HTTP $code"
        return ApiException(code, msg)
    }

    companion object {
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()

        fun normalizeBaseUrl(raw: String): String {
            var u = raw.trim()
            if (u.isEmpty()) throw IllegalArgumentException("Backend URL is empty")
            if (!u.contains("://")) u = "https://$u"
            u = u.trimEnd('/')
            val lower = u.lowercase()
            if (lower.startsWith("https://")) return u
            if (lower.startsWith("http://")) {
                var host = u.substring("http://".length).substringBefore('/').substringBefore('?')
                host = host.substringAfterLast('@').substringBefore(':').lowercase()
                if (host == "localhost" || host == "127.0.0.1" || host == "10.0.2.2") return u
            }
            throw IllegalArgumentException("Use an https:// URL")
        }

        private fun optStr(o: JSONObject, vararg keys: String): String? {
            for (k in keys) {
                if (o.has(k) && !o.isNull(k)) return o.get(k).toString()
            }
            return null
        }

        private fun strList(o: JSONObject, vararg keys: String): List<String> {
            for (k in keys) {
                val arr = o.optJSONArray(k) ?: continue
                val out = ArrayList<String>()
                for (i in 0 until arr.length()) {
                    if (!arr.isNull(i)) out.add(arr.get(i).toString())
                }
                return out
            }
            return emptyList()
        }

        private fun parseRecipe(o: JSONObject): RecipePreview {
            val total: Int = run {
                val v = if (o.has("totalTime")) o.opt("totalTime") else o.opt("total_time")
                when (v) {
                    is Number -> v.toInt()
                    is String -> v.trim().toIntOrNull()
                        ?: v.trim().takeWhile { it.isDigit() }.toIntOrNull()
                        ?: 0
                    else -> 0
                }
            }
            return RecipePreview(
                title = optStr(o, "title") ?: "",
                description = optStr(o, "description") ?: "",
                preparationTime = optStr(o, "preparationTime", "preparation_time") ?: "",
                cookingTime = optStr(o, "cookingTime", "cooking_time") ?: "",
                totalTime = total,
                quantity = optStr(o, "quantity") ?: "",
                category = optStr(o, "category") ?: "",
                cookware = strList(o, "cookware"),
                ingredients = strList(o, "ingredients"),
                instructions = strList(o, "instructions")
            )
        }

        internal fun parseJobStatus(json: String): JobStatus {
            val o = JSONObject(json)
            val kind = when (optStr(o, "status")?.trim()?.lowercase()) {
                "running" -> JobStatusKind.RUNNING
                "done" -> JobStatusKind.DONE
                "error" -> JobStatusKind.ERROR
                else -> JobStatusKind.QUEUED
            }
            val recipeObj = if (o.isNull("recipe")) null else o.optJSONObject("recipe")
            return JobStatus(
                id = optStr(o, "id") ?: "",
                kind = kind,
                error = optStr(o, "error"),
                title = optStr(o, "title"),
                source = optStr(o, "source"),
                recipe = recipeObj?.let { parseRecipe(it) }
            )
        }

        internal fun parseFilename(contentDisposition: String?): String {
            val fallback = "recipe.rtk"
            if (contentDisposition.isNullOrBlank()) return fallback
            val m = Regex("filename\\*?=\\s*(?:\"([^\"]*)\"|([^;]+))", RegexOption.IGNORE_CASE)
                .find(contentDisposition) ?: return fallback
            val rawName = (m.groups[1]?.value ?: m.groups[2]?.value ?: "").trim()
            // drop any path components
            val base = rawName.substringAfterLast('/').substringAfterLast('\\')
            val clean = base.map { c ->
                if (c in 'A'..'Z' || c in 'a'..'z' || c in '0'..'9' || c == '.' || c == '_' || c == '-') c else '_'
            }.joinToString("")
            if (clean.isEmpty() || clean.all { it == '.' || it == '_' }) return fallback
            return if (clean.lowercase().endsWith(".rtk")) clean else "$clean.rtk"
        }
    }
}
