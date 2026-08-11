package com.vlessboost.app

import android.app.Application
import android.util.Log
import io.nekohasekai.libbox.Libbox
import io.nekohasekai.libbox.SetupOptions
import java.io.File

class BoostApp : Application() {
    override fun onCreate() {
        super.onCreate()
        instance = this
        val base = filesDir
        val working = File(base, "sing-box").also { it.mkdirs() }
        val temp = File(cacheDir, "sing-box").also { it.mkdirs() }
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
    }

    companion object {
        private const val TAG = "BoostApp"
        lateinit var instance: BoostApp
            private set
    }
}
