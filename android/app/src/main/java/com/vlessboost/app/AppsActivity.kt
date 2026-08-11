package com.vlessboost.app

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.vlessboost.app.databinding.ActivityAppsBinding
import com.vlessboost.app.databinding.ItemAppBinding

data class AppRow(
    val packageName: String,
    val label: String,
    val icon: android.graphics.drawable.Drawable?,
    var selected: Boolean,
)

class AppsActivity : AppCompatActivity() {
    private lateinit var binding: ActivityAppsBinding
    private lateinit var prefs: Prefs
    private val all = mutableListOf<AppRow>()
    private val visible = mutableListOf<AppRow>()
    private lateinit var adapter: AppsAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityAppsBinding.inflate(layoutInflater)
        setContentView(binding.root)
        prefs = Prefs(this)

        adapter = AppsAdapter(visible)
        binding.appsList.layoutManager = LinearLayoutManager(this)
        binding.appsList.adapter = adapter

        binding.btnSaveApps.setOnClickListener {
            prefs.selectedApps = all.filter { it.selected }.map { it.packageName }.toSet()
            finish()
        }

        binding.searchApps.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) {
                filter(s?.toString().orEmpty())
            }
        })

        Thread {
            val selected = prefs.selectedApps
            val pm = packageManager
            // Все приложения с иконкой на рабочем столе — включая системные (YouTube и т.п.)
            val launchable = launchablePackages(pm)
            val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
                .asSequence()
                .filter { app ->
                    app.packageName != packageName && app.packageName in launchable
                }
                .map { app ->
                    AppRow(
                        packageName = app.packageName,
                        label = pm.getApplicationLabel(app).toString(),
                        icon = runCatching { pm.getApplicationIcon(app) }.getOrNull(),
                        selected = selected.contains(app.packageName),
                    )
                }
                .sortedWith(compareByDescending<AppRow> { it.selected }.thenBy { it.label.lowercase() })
                .toList()
            runOnUiThread {
                all.clear()
                all.addAll(apps)
                filter(binding.searchApps.text?.toString().orEmpty())
            }
        }.start()
    }

    private fun launchablePackages(pm: PackageManager): Set<String> {
        val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val flags = PackageManager.MATCH_ALL
        return pm.queryIntentActivities(intent, flags)
            .mapNotNull { it.activityInfo?.packageName }
            .toSet()
    }

    private fun filter(query: String) {
        val q = query.trim().lowercase()
        visible.clear()
        if (q.isEmpty()) {
            visible.addAll(all)
        } else {
            visible.addAll(all.filter {
                it.label.lowercase().contains(q) || it.packageName.lowercase().contains(q)
            })
        }
        adapter.notifyDataSetChanged()
    }
}

class AppsAdapter(private val items: List<AppRow>) :
    RecyclerView.Adapter<AppsAdapter.VH>() {

    class VH(val binding: ItemAppBinding) : RecyclerView.ViewHolder(binding.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val binding = ItemAppBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return VH(binding)
    }

    override fun getItemCount(): Int = items.size

    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        holder.binding.appName.text = item.label
        holder.binding.appPackage.text = item.packageName
        holder.binding.appIcon.setImageDrawable(item.icon)
        holder.binding.appSwitch.setOnCheckedChangeListener(null)
        holder.binding.appSwitch.isChecked = item.selected
        holder.binding.appSwitch.setOnCheckedChangeListener { _, checked ->
            item.selected = checked
        }
        holder.binding.root.setOnClickListener {
            holder.binding.appSwitch.isChecked = !holder.binding.appSwitch.isChecked
        }
    }
}
