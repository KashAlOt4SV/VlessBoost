package com.vlessboost.app

import android.util.Log
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Простые обновления по URL version.json.
 * Dual-fetch: raw GitHub + jsDelivr, берём более новый versionCode.
 */
object UpdateChecker {
    val MANIFEST_URLS = listOf(
        "https://raw.githubusercontent.com/KashAlOt4SV/VlessBoost/main/update/version.json",
        "https://cdn.jsdelivr.net/gh/KashAlOt4SV/VlessBoost@main/update/version.json",
    )

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
        var best: AndroidUpdate? = null
        var lastError: String? = null
        for (base in MANIFEST_URLS) {
            val root = fetchManifest(base)
            if (root == null) {
                lastError = "Не удалось скачать version.json"
                continue
            }
            val android = root.optJSONObject("android")
            if (android == null) {
                lastError = "В version.json нет блока android"
                continue
            }
            val code = android.optInt("versionCode", 0)
            val name = android.optString("versionName", "")
            val url = android.optString("url", "")
            if (url.isBlank()) {
                lastError = "В version.json пустой url"
                continue
            }
            if (code <= 0) {
                lastError = "Некорректный versionCode в version.json"
                continue
            }
            val cand = AndroidUpdate(code, name, url)
            if (best == null || cand.versionCode > best.versionCode) {
                best = cand
            }
        }
        val remote = best
            ?: return CheckResult.Failed(lastError ?: "Не удалось скачать version.json")
        if (remote.versionCode <= currentCode) {
            return CheckResult.UpToDate(currentCode, remote.versionCode, remote.versionName)
        }
        return CheckResult.Available(remote)
    }

    /** @deprecated используйте checkAndroidDetailed */
    fun checkAndroid(currentCode: Int): AndroidUpdate? =
        (checkAndroidDetailed(currentCode) as? CheckResult.Available)?.update

    private fun fetchManifest(baseUrl: String): JSONObject? {
        return try {
            val url = URL("$baseUrl?t=${System.currentTimeMillis()}")
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
                Log.w("UpdateChecker", "HTTP $code from $baseUrl")
                return null
            }
            conn.inputStream.bufferedReader().use { reader ->
                JSONObject(reader.readText())
            }
        } catch (e: Exception) {
            Log.w("UpdateChecker", "manifest ($baseUrl): ${e.message}")
            null
        }
    }
}
