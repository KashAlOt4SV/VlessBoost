package com.vlessboost.app

import android.content.ClipData
import android.content.ClipboardManager
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.vlessboost.app.databinding.ActivityLogsBinding

class LogsActivity : AppCompatActivity() {
    private lateinit var binding: ActivityLogsBinding
    private val listener: (String) -> Unit = { line ->
        runOnUiThread {
            if (line.isEmpty()) {
                binding.logsText.text = ""
            } else {
                binding.logsText.append(line + "\n")
                binding.logsScroll.post {
                    binding.logsScroll.fullScroll(android.view.View.FOCUS_DOWN)
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityLogsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val mem = LogStore.snapshot()
        binding.logsText.text = if (mem.isNotBlank()) {
            mem
        } else {
            val disk = LogStore.readPersisted()
            if (disk.isNotBlank()) "—— last session (disk) ——\n$disk" else ""
        }
        binding.btnClearLogs.setOnClickListener { LogStore.clear() }
        binding.btnCopyLogs.setOnClickListener {
            val cm = getSystemService(ClipboardManager::class.java)
            val text = LogStore.snapshot().ifBlank { LogStore.readPersisted() }
            cm.setPrimaryClip(ClipData.newPlainText("logs", text))
            Toast.makeText(this, "Логи скопированы", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onStart() {
        super.onStart()
        LogStore.addListener(listener)
        binding.logsText.text = LogStore.snapshot()
    }

    override fun onStop() {
        LogStore.removeListener(listener)
        super.onStop()
    }
}
