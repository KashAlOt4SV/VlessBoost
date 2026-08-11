package com.vlessboost.app

import android.Manifest
import android.app.DownloadManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.Uri
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.google.android.material.chip.Chip
import com.vlessboost.app.databinding.ActivityMainBinding
import com.vlessboost.app.vpn.BoostVpnService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var prefs: Prefs
    private val scope = CoroutineScope(Dispatchers.Main + Job())
    private var downloadId: Long = -1

    private val vpnPermission = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            BoostVpnService.start(this)
        } else {
            Toast.makeText(this, R.string.vpn_permission, Toast.LENGTH_LONG).show()
        }
    }

    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { /* optional */ }

    private val installPermission = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) {
        // user returned from unknown sources settings
    }

    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val running = intent?.getBooleanExtra(BoostVpnService.EXTRA_RUNNING, false) == true
            val err = intent?.getStringExtra(BoostVpnService.EXTRA_ERROR)
            updateUi(running)
            if (!err.isNullOrBlank()) {
                Toast.makeText(this@MainActivity, err, Toast.LENGTH_LONG).show()
            }
        }
    }

    private val downloadReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val id = intent?.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1) ?: return
            if (id != downloadId) return
            val query = DownloadManager.Query().setFilterById(id)
            val dm = getSystemService(DownloadManager::class.java)
            dm.query(query)?.use { c ->
                if (!c.moveToFirst()) return
                val status = c.getInt(c.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS))
                if (status == DownloadManager.STATUS_SUCCESSFUL) {
                    val uri = dm.getUriForDownloadedFile(id) ?: return
                    installApk(uri)
                } else {
                    Toast.makeText(this@MainActivity, "Скачивание не удалось", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        binding.vlessInput.setText(prefs.vlessUrl)
        bindPresets()
        updateAppsSummary()
        updateUi(BoostVpnService.isRunning)

        binding.btnApps.setOnClickListener {
            startActivity(Intent(this, AppsActivity::class.java))
        }
        binding.btnLogs.setOnClickListener {
            startActivity(Intent(this, LogsActivity::class.java))
        }
        binding.btnUpdate.setOnClickListener { checkUpdate() }

        binding.btnBoost.setOnClickListener {
            if (BoostVpnService.isRunning) {
                BoostVpnService.stop(this)
                updateUi(false)
            } else {
                startBoost()
            }
        }

        if (Build.VERSION.SDK_INT >= 33) {
            notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    override fun onResume() {
        super.onResume()
        updateAppsSummary()
        updateUi(BoostVpnService.isRunning)
        ContextCompat.registerReceiver(
            this,
            statusReceiver,
            IntentFilter(BoostVpnService.ACTION_STATUS),
            ContextCompat.RECEIVER_NOT_EXPORTED,
        )
        ContextCompat.registerReceiver(
            this,
            downloadReceiver,
            IntentFilter(DownloadManager.ACTION_DOWNLOAD_COMPLETE),
            ContextCompat.RECEIVER_EXPORTED,
        )
    }

    override fun onPause() {
        runCatching { unregisterReceiver(statusReceiver) }
        runCatching { unregisterReceiver(downloadReceiver) }
        super.onPause()
    }

    private fun bindPresets() {
        binding.presetChips.removeAllViews()
        val selected = prefs.selectedPresets.toMutableSet()
        Presets.all.forEach { preset ->
            val chip = Chip(this).apply {
                text = preset.title
                isCheckable = true
                isChecked = selected.contains(preset.id)
                setOnCheckedChangeListener { _, checked ->
                    if (checked) selected.add(preset.id) else selected.remove(preset.id)
                    prefs.selectedPresets = selected
                }
            }
            binding.presetChips.addView(chip)
        }
    }

    private fun updateAppsSummary() {
        val n = prefs.selectedApps.size
        binding.appsSummary.text = if (n == 0) {
            "Приложения не выбраны"
        } else {
            "Выбрано приложений: $n"
        }
    }

    private fun startBoost() {
        val url = binding.vlessInput.text?.toString()?.trim().orEmpty()
        if (url.isBlank()) {
            Toast.makeText(this, R.string.need_link, Toast.LENGTH_SHORT).show()
            return
        }
        if (prefs.selectedApps.isEmpty()) {
            Toast.makeText(this, R.string.select_apps, Toast.LENGTH_SHORT).show()
            return
        }
        try {
            VlessParser.parse(url)
        } catch (e: Exception) {
            Toast.makeText(this, e.message ?: "Некорректная ссылка", Toast.LENGTH_LONG).show()
            return
        }
        prefs.vlessUrl = url
        LogStore.append("UI: starting boost…")

        val prepare = VpnService.prepare(this)
        if (prepare != null) {
            vpnPermission.launch(prepare)
        } else {
            BoostVpnService.start(this)
            updateUi(true)
        }
    }

    private fun updateUi(running: Boolean) {
        binding.statusText.text = if (running) getString(R.string.status_on) else getString(R.string.status_off)
        binding.statusText.setTextColor(
            ContextCompat.getColor(this, if (running) R.color.ok else R.color.muted),
        )
        binding.btnBoost.text = if (running) getString(R.string.boost_off) else getString(R.string.boost_on)
        binding.btnBoost.setBackgroundColor(
            ContextCompat.getColor(this, if (running) R.color.danger else R.color.accent),
        )
    }

    private fun checkUpdate() {
        Toast.makeText(this, "Проверка обновлений…", Toast.LENGTH_SHORT).show()
        scope.launch {
            val update = withContext(Dispatchers.IO) {
                UpdateChecker.checkAndroid(BuildConfig.VERSION_CODE)
            }
            if (update == null) {
                Toast.makeText(
                    this@MainActivity,
                    "Обновлений нет (v${BuildConfig.VERSION_NAME})",
                    Toast.LENGTH_SHORT,
                ).show()
                return@launch
            }
            AlertDialog.Builder(this@MainActivity)
                .setTitle("Доступно обновление ${update.versionName}")
                .setMessage("Скачать и установить?")
                .setPositiveButton("Скачать") { _, _ -> downloadApk(update.url, update.versionName) }
                .setNegativeButton("Позже", null)
                .show()
        }
    }

    private fun downloadApk(url: String, versionName: String) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
            Toast.makeText(this, "Разрешите установку из неизвестных источников", Toast.LENGTH_LONG).show()
            installPermission.launch(
                Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")),
            )
        }
        val req = DownloadManager.Request(Uri.parse(url))
            .setTitle("VLESS Boost $versionName")
            .setDescription("Скачивание обновления")
            .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
            .setDestinationInExternalFilesDir(this, Environment.DIRECTORY_DOWNLOADS, "VLESS-Boost-$versionName.apk")
        val dm = getSystemService(DownloadManager::class.java)
        downloadId = dm.enqueue(req)
        Toast.makeText(this, "Скачивание началось", Toast.LENGTH_SHORT).show()
    }

    private fun installApk(uri: Uri) {
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            // fallback через FileProvider если uri file://
            val path = uri.path
            if (path != null) {
                val file = File(path)
                val contentUri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
                startActivity(
                    Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(contentUri, "application/vnd.android.package-archive")
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                    },
                )
            } else {
                Toast.makeText(this, "Не удалось открыть APK: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }
}
