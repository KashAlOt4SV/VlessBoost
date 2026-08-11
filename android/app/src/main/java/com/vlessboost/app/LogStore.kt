package com.vlessboost.app

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CopyOnWriteArrayList

/** Кольцевой буфер логов VPN для экрана отладки. */
object LogStore {
    private const val MAX = 2500
    private val lines = ArrayDeque<String>()
    private val listeners = CopyOnWriteArrayList<(String) -> Unit>()
    private val fmt = SimpleDateFormat("HH:mm:ss", Locale.US)

    @Synchronized
    fun clear() {
        lines.clear()
        listeners.forEach { it.invoke("") }
    }

    @Synchronized
    fun append(message: String) {
        val text = message.trimEnd()
        if (text.isEmpty()) return
        val stamped = "${fmt.format(Date())}  $text"
        lines.addLast(stamped)
        while (lines.size > MAX) lines.removeFirst()
        listeners.forEach { it.invoke(stamped) }
    }

    @Synchronized
    fun snapshot(): String = lines.joinToString("\n")

    fun addListener(listener: (String) -> Unit) {
        listeners.add(listener)
    }

    fun removeListener(listener: (String) -> Unit) {
        listeners.remove(listener)
    }
}
