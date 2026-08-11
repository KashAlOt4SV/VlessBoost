package com.vlessboost.app

import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Простые обновления по URL version.json.
 */
object UpdateChecker {
    const val MANIFEST_URL =
        "https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json"

    data class AndroidUpdate(
        val versionCode: Int,
        val versionName: String,
        val url: String,
    )

    sealed class CheckResult {
        data class Available(val update: AndroidUpdate) : CheckResult()
        data class UpToDate(val currentCode: Int, val remoteCode: Int, val remoteName: String) : CheckResult()
        data class Failed(val reason: String) : CheckResult()
    }

    fun checkAndroidDetailed(currentCode: Int): CheckResult {
        val root = fetchManifest()
            ?: return CheckResult.Failed("Не удалось скачать version.json")
        val android = root.optJSONObject("android")
            ?: return CheckResult.Failed("В version.json нет блока android")
        val code = android.optInt("versionCode", 0)
        val name = android.optString("versionName", "")
        val url = android.optString("url", "")
        if (url.isBlank()) {
            return CheckResult.Failed("В version.json пустой url")
        }
        if (code <= 0) {
            return CheckResult.Failed("Некорректный versionCode в version.json")
        }
        if (code <= currentCode) {
            return CheckResult.UpToDate(currentCode, code, name)
        }
        return CheckResult.Available(AndroidUpdate(code, name, url))
    }

    /** @deprecated используйте checkAndroidDetailed */
    fun checkAndroid(currentCode: Int): AndroidUpdate? =
        (checkAndroidDetailed(currentCode) as? CheckResult.Available)?.update

    private fun fetchManifest(): JSONObject? {
        return try {
            val url = URL("$MANIFEST_URL?t=${System.currentTimeMillis()}")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 10000
                readTimeout = 15000
                requestMethod = "GET"
                useCaches = false
                setRequestProperty("Cache-Control", "no-cache")
                setRequestProperty("Accept", "application/json")
                setRequestProperty("User-Agent", "VLESS-Boost-Android")
            }
            val code = conn.responseCode
            if (code !in 200..299) {
                Log.w("UpdateChecker", "HTTP $code")
                return null
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
