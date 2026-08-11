package com.vlessboost.app

import android.content.Context
import android.content.SharedPreferences

class Prefs(context: Context) {
    private val sp: SharedPreferences =
        context.getSharedPreferences("vless_boost", Context.MODE_PRIVATE)

    var vlessUrl: String
        get() = sp.getString(KEY_URL, "") ?: ""
        set(value) = sp.edit().putString(KEY_URL, value).apply()

    var selectedApps: Set<String>
        get() = sp.getStringSet(KEY_APPS, emptySet()) ?: emptySet()
        set(value) = sp.edit().putStringSet(KEY_APPS, value.toSet()).apply()

    var selectedPresets: Set<String>
        get() = sp.getStringSet(KEY_PRESETS, setOf("discord", "youtube")) ?: emptySet()
        set(value) = sp.edit().putStringSet(KEY_PRESETS, value.toSet()).apply()

    companion object {
        private const val KEY_URL = "vless_url"
        private const val KEY_APPS = "selected_apps"
        private const val KEY_PRESETS = "selected_presets"
    }
}
