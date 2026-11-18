package com.recimport.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.recimport.app.net.ApiClient
import com.recimport.app.net.ApiException
import com.recimport.app.net.JobStatusKind
import com.recimport.app.net.RecipePreview
import com.recimport.app.net.RtkFile
import com.recimport.app.net.Settings
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface UiState {
    object Idle : UiState
    data class Working(val message: String) : UiState
    data class Done(val recipe: RecipePreview?, val title: String, val file: RtkFile) : UiState
    data class Failed(val message: String) : UiState
}

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val store = SettingsStore(app)
    private val api = ApiClient()
    private val _state = MutableStateFlow<UiState>(UiState.Idle)
    val state: StateFlow<UiState> = _state.asStateFlow()
    private var job: Job? = null

    fun loadSettings(): Settings = store.load()

    fun saveSettings(baseUrl: String, token: String, geminiKey: String) {
        store.baseUrl = baseUrl.trim()
        store.token = token.trim()
        store.geminiKey = geminiKey.trim()
    }

    fun reset() {
        job?.cancel()
        _state.value = UiState.Idle
    }

    fun start(text: String) {
        job?.cancel()
        if (!store.isConfigured) {
            _state.value = UiState.Failed("Open Settings and enter the backend URL and app token")
            return
        }
        job = viewModelScope.launch(Dispatchers.IO) {
            try {
                val base = try {
                    ApiClient.normalizeBaseUrl(store.baseUrl)
                } catch (e: IllegalArgumentException) {
                    _state.value = UiState.Failed(e.message ?: "Invalid backend URL")
                    return@launch
                }
                val s = Settings(base, store.token, store.geminiKey)
                _state.value = UiState.Working("Waking the server (the first request can take a minute)…")
                val reason = api.checkServer(base)
                if (reason != null) {
                    _state.value = UiState.Failed(reason)
                    return@launch
                }
                _state.value = UiState.Working("Sending link…")
                val id = api.createJob(s, text.trim())
                val deadline = System.currentTimeMillis() + 4 * 60 * 1000L
                var failures = 0
                while (System.currentTimeMillis() < deadline) {
                    delay(2000)
                    val st = try {
                        api.getJob(s, id).also { failures = 0 }
                    } catch (e: ApiException) {
                        failures++
                        if ((e.code == 0 || e.code >= 500) && failures <= 3) continue
                        throw e
                    }
                    when (st.kind) {
                        JobStatusKind.QUEUED -> _state.value = UiState.Working("Queued…")
                        JobStatusKind.RUNNING -> _state.value = UiState.Working("Working on the recipe…")
                        JobStatusKind.ERROR -> {
                            _state.value = UiState.Failed(st.error ?: "Extraction failed")
                            return@launch
                        }
                        JobStatusKind.DONE -> {
                            _state.value = UiState.Working("Preparing file…")
                            val file = api.downloadRtk(s, id)
                            _state.value = UiState.Done(
                                st.recipe,
                                st.title ?: st.recipe?.title ?: file.filename,
                                file
                            )
                            return@launch
                        }
                    }
                }
                _state.value = UiState.Failed("Timed out")
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                _state.value = UiState.Failed(e.message ?: "Request failed")
            } catch (e: Exception) {
                _state.value = UiState.Failed(e.message ?: "Unexpected error")
            }
        }
    }
}
