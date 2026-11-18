package com.recimport.app.net

data class Settings(val baseUrl: String, val token: String, val geminiKey: String = "")

data class RecipePreview(
    val title: String,
    val description: String,
    val preparationTime: String,
    val cookingTime: String,
    val totalTime: Int,
    val quantity: String,
    val category: String,
    val cookware: List<String>,
    val ingredients: List<String>,
    val instructions: List<String>
)

enum class JobStatusKind { QUEUED, RUNNING, DONE, ERROR }

data class JobStatus(
    val id: String,
    val kind: JobStatusKind,
    val error: String?,
    val title: String?,
    val source: String?,
    val recipe: RecipePreview?
)

class RtkFile(val filename: String, val bytes: ByteArray)

class ApiException(val code: Int, message: String) : Exception(message) // code 0 = network failure
