package com.recimport.app

import android.content.Context
import android.content.SharedPreferences
import com.recimport.app.net.Settings

class SettingsStore(context: Context) {
    private val prefs: SharedPreferences =
        context.applicationContext.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString("baseUrl", "") ?: ""
        set(v) { prefs.edit().putString("baseUrl", v).apply() }

    var token: String
        get() = prefs.getString("token", "") ?: ""
        set(v) { prefs.edit().putString("token", v).apply() }

    var geminiKey: String
        get() = prefs.getString("geminiKey", "") ?: ""
        set(v) { prefs.edit().putString("geminiKey", v).apply() }

    fun load(): Settings = Settings(baseUrl, token, geminiKey)

    val isConfigured: Boolean
        get() = baseUrl.isNotBlank() && token.isNotBlank()
}
