package com.vlessboost.app.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.vlessboost.app.LogStore
import io.nekohasekai.libbox.InterfaceUpdateListener
import java.net.NetworkInterface as JavaNetworkInterface
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/**
 * Следит за реальной сетью (Wi‑Fi/LTE), исключая VPN —
 * без этого sing-box пишет "no available network interface".
 *
 * Важно: updateDefaultInterface вызывается с одной очереди и с generation-check,
 * иначе параллельные вызовы / use-after-free Go-объекта роняют процесс без FATAL в LogStore.
 */
object DefaultNetworkMonitor {
    private const val TAG = "DefaultNetMon"

    @Volatile
    var underlying: Network? = null
        private set

    @Volatile
    private var listener: InterfaceUpdateListener? = null
    private var registered = false
    private var cm: ConnectivityManager? = null
    private val mainHandler = Handler(Looper.getMainLooper())
    private val notifyExecutor = Executors.newSingleThreadExecutor { r ->
        Thread(r, "default-net-mon").apply { isDaemon = true }
    }
    private val resolveGeneration = AtomicInteger(0)

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            if (isVpnNetwork(network)) return
            underlying = network
            notifyListener(network)
        }

        override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
            if (networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) return
            if (network == underlying) notifyListener(network)
        }

        override fun onLost(network: Network) {
            if (network == underlying) {
                underlying = null
                // попробуем другую сеть, иначе очистим
                val connectivity = cm
                if (connectivity != null) {
                    pickInitial(connectivity)
                    if (underlying == null) notifyListener(null)
                } else {
                    notifyListener(null)
                }
            }
        }
    }

    fun start(context: Context) {
        if (registered) return
        cm = context.applicationContext.getSystemService(ConnectivityManager::class.java)
        val connectivity = cm ?: return
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_RESTRICTED)
            .apply {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    addCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
                }
            }
            .build()
        try {
            // Только наблюдение — requestNetwork держит сеть и после TUN даёт гонки.
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                connectivity.registerBestMatchingNetworkCallback(request, callback, mainHandler)
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                connectivity.registerNetworkCallback(request, callback, mainHandler)
            } else {
                connectivity.registerNetworkCallback(request, callback)
            }
            registered = true
            pickInitial(connectivity)
            LogStore.append("network monitor started")
        } catch (e: Exception) {
            Log.e(TAG, "register failed", e)
            LogStore.append("network monitor error: ${e.message}")
            pickInitial(connectivity)
        }
    }

    fun stop() {
        resolveGeneration.incrementAndGet()
        val connectivity = cm
        if (registered && connectivity != null) {
            runCatching { connectivity.unregisterNetworkCallback(callback) }
        }
        registered = false
        underlying = null
        listener = null
        cm = null
    }

    fun setListener(updateListener: InterfaceUpdateListener?) {
        listener = updateListener
        notifyListener(underlying)
    }

    private fun isVpnNetwork(network: Network): Boolean {
        val caps = cm?.getNetworkCapabilities(network) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
    }

    private fun pickInitial(connectivity: ConnectivityManager) {
        for (network in connectivity.allNetworks) {
            val caps = connectivity.getNetworkCapabilities(network) ?: continue
            if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) continue
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) continue
            underlying = network
            notifyListener(network)
            return
        }
        val active = connectivity.activeNetwork
        if (active != null) {
            val caps = connectivity.getNetworkCapabilities(active)
            if (caps != null && !caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
                underlying = active
                notifyListener(active)
            }
        }
    }

    private fun notifyListener(network: Network?) {
        val updateListener = listener ?: return
        val connectivity = cm ?: return
        val gen = resolveGeneration.incrementAndGet()

        if (network == null) {
            notifyExecutor.execute {
                if (gen != resolveGeneration.get()) return@execute
                if (listener !== updateListener) return@execute
                runCatching {
                    updateListener.updateDefaultInterface("", -1, false, false)
                }.onFailure {
                    LogStore.append("updateDefaultInterface(clear) error: ${it.message}")
                    Log.w(TAG, "updateDefaultInterface clear", it)
                }
            }
            return
        }

        notifyExecutor.execute {
            repeat(15) { attempt ->
                if (gen != resolveGeneration.get()) return@execute
                if (listener !== updateListener) return@execute
                try {
                    val lp = connectivity.getLinkProperties(network)
                    val name = lp?.interfaceName
                    if (!name.isNullOrBlank()) {
                        val index = try {
                            JavaNetworkInterface.getByName(name)?.index ?: -1
                        } catch (_: Exception) {
                            -1
                        }
                        if (index >= 0) {
                            LogStore.append("default iface=$name index=$index (try=$attempt)")
                            runCatching {
                                updateListener.updateDefaultInterface(name, index, false, false)
                            }.onFailure {
                                LogStore.append("updateDefaultInterface error: ${it.message}")
                                Log.w(TAG, "updateDefaultInterface", it)
                            }
                            return@execute
                        }
                    }
                } catch (e: Exception) {
                    LogStore.append("default iface resolve error: ${e.message}")
                    Log.w(TAG, "resolve", e)
                }
                try {
                    Thread.sleep(100)
                } catch (_: InterruptedException) {
                    return@execute
                }
            }
            if (gen != resolveGeneration.get() || listener !== updateListener) return@execute
            LogStore.append("default iface: failed to resolve")
            runCatching { updateListener.updateDefaultInterface("", -1, false, false) }
                .onFailure { LogStore.append("updateDefaultInterface(fail) error: ${it.message}") }
        }
    }
}
