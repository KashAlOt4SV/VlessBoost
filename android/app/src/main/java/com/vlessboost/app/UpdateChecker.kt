package com.vlessboost.app

import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Простые обновления по URL version.json:
 * {
 *   "android": { "versionCode": 2, "versionName": "1.0.1", "url": "https://.../VLESS-Boost.apk" },
 *   "windows": { "version": "1.0.1", "url": "https://.../VLESS-Boost.exe" }
 * }
 */
object UpdateChecker {
    // Можно заменить на свой GitHub Releases / raw URL
    const val MANIFEST_URL =
        "https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json"

    data class AndroidUpdate(
        val versionCode: Int,
        val versionName: String,
        val url: String,
    )

    fun checkAndroid(currentCode: Int): AndroidUpdate? {
        val root = fetchManifest() ?: return null
        val android = root.optJSONObject("android") ?: return null
        val code = android.optInt("versionCode", 0)
        val name = android.optString("versionName", "")
        val url = android.optString("url", "")
        if (code <= currentCode || url.isBlank()) return null
        return AndroidUpdate(code, name, url)
    }

    private fun fetchManifest(): JSONObject? {
        return try {
            val conn = (URL(MANIFEST_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10000
                readTimeout = 15000
                requestMethod = "GET"
                setRequestProperty("Accept", "application/json")
            }
            conn.inputStream.bufferedReader().use { reader ->
                JSONObject(reader.readText())
            }
        } catch (e: Exception) {
            Log.w("UpdateChecker", "manifest: ${e.message}")
            null
        }
    }
}
