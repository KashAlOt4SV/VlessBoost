package com.vlessboost.app

import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CopyOnWriteArrayList

/** Кольцевой буфер логов VPN для экрана отладки + файл на диск (переживает native death). */
object LogStore {
    private const val MAX = 2500
    private const val TAG = "LogStore"
    private val lines = ArrayDeque<String>()
    private val listeners = CopyOnWriteArrayList<(String) -> Unit>()
    private val fmt = SimpleDateFormat("HH:mm:ss", Locale.US)

    @Volatile
    private var logFile: File? = null

    fun init(filesDir: File) {
        val dir = File(filesDir, "logs").also { it.mkdirs() }
        logFile = File(dir, "vpn-last.log")
    }

    @Synchronized
    fun clear() {
        lines.clear()
        listeners.forEach { it.invoke("") }
        runCatching { logFile?.writeText("") }
    }

    @Synchronized
    fun append(message: String) {
        val text = message.trimEnd()
        if (text.isEmpty()) return
        val stamped = "${fmt.format(Date())}  $text"
        lines.addLast(stamped)
        while (lines.size > MAX) lines.removeFirst()
        listeners.forEach { it.invoke(stamped) }
        // Сразу на диск — иначе silent native crash теряет последние строки.
        runCatching {
            logFile?.appendText(stamped + "\n")
        }.onFailure {
            Log.w(TAG, "persist failed", it)
        }
    }

    @Synchronized
    fun snapshot(): String = lines.joinToString("\n")

    fun readPersisted(): String =
        runCatching { logFile?.takeIf { it.exists() }?.readText().orEmpty() }.getOrDefault("")

    fun addListener(listener: (String) -> Unit) {
        listeners.add(listener)
    }

    fun removeListener(listener: (String) -> Unit) {
        listeners.remove(listener)
    }
}
