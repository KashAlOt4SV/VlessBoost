package com.vlessboost.app

import android.app.Application
import android.util.Log
import go.Seq
import io.nekohasekai.libbox.Libbox
import io.nekohasekai.libbox.SetupOptions
import java.io.File

class BoostApp : Application() {
    override fun onCreate() {
        super.onCreate()
        instance = this
        LogStore.init(filesDir)
        val prev = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            runCatching {
                LogStore.append("FATAL thread=${t.name}: ${e.javaClass.simpleName}: ${e.message}")
                e.stackTrace.take(12).forEach { LogStore.append("  at $it") }
            }
            Log.e(TAG, "uncaught on ${t.name}", e)
            prev?.uncaughtException(t, e)
        }
        // Required for gomobile/libbox on Android 10+ (no AppGlobals reflection).
        Seq.setContext(this)
        val base = filesDir
        val working = File(base, "sing-box").also { it.mkdirs() }
        val temp = File(cacheDir, "sing-box").also { it.mkdirs() }
        try {
            Libbox.setup(
                SetupOptions().apply {
                    basePath = base.absolutePath
                    workingPath = working.absolutePath
                    tempPath = temp.absolutePath
                    fixAndroidStack = true
                    logMaxLines = 300
                },
            )
            Libbox.setLocale("ru")
            Log.i(TAG, "libbox ${Libbox.version()}")
            LogStore.append("libbox ${Libbox.version()} ready")
        } catch (e: Throwable) {
            // Never take down the whole process on UI launch if native init fails.
            Log.e(TAG, "libbox setup failed", e)
            runCatching { LogStore.append("libbox setup failed: ${e.message}") }
        }
    }

    companion object {
        private const val TAG = "BoostApp"
        lateinit var instance: BoostApp
            private set
    }
}
