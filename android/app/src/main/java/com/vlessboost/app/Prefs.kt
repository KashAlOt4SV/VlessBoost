package com.vlessboost.app

import android.content.Context
import android.content.SharedPreferences
import java.io.File

class Prefs(context: Context) {
    private val appContext = context.applicationContext
    private val sp: SharedPreferences =
        appContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val backupFile: File = File(appContext.filesDir, BACKUP_FILE)

    init {
        // Recover link if SharedPreferences was wiped but backup remains (rare, but OTA-safe).
        if (vlessUrl.isBlank() && backupFile.exists()) {
            val recovered = runCatching { backupFile.readText(Charsets.UTF_8).trim() }.getOrNull().orEmpty()
            if (recovered.isNotBlank()) {
                sp.edit().putString(KEY_URL, recovered).commit()
            }
        }
    }

    var vlessUrl: String
        get() = sp.getString(KEY_URL, "") ?: ""
        set(value) {
            val trimmed = value.trim()
            sp.edit().putString(KEY_URL, trimmed).commit()
            runCatching {
                if (trimmed.isBlank()) {
                    if (backupFile.exists()) backupFile.delete()
                } else {
                    backupFile.writeText(trimmed, Charsets.UTF_8)
                }
            }
        }

    var selectedApps: Set<String>
        get() = sp.getStringSet(KEY_APPS, emptySet())?.toSet() ?: emptySet()
        set(value) {
            sp.edit().putStringSet(KEY_APPS, value.toSet()).commit()
        }

    var selectedPresets: Set<String>
        get() = sp.getStringSet(KEY_PRESETS, setOf("discord", "youtube"))?.toSet() ?: emptySet()
        set(value) {
            sp.edit().putStringSet(KEY_PRESETS, value.toSet()).commit()
        }

    companion object {
        private const val PREFS_NAME = "vless_boost"
        private const val KEY_URL = "vless_url"
        private const val KEY_APPS = "selected_apps"
        private const val KEY_PRESETS = "selected_presets"
        private const val BACKUP_FILE = "vless_url.backup.txt"
    }
}
