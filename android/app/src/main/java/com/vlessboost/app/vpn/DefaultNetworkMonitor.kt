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

/**
 * Следит за реальной сетью (Wi‑Fi/LTE), исключая VPN —
 * без этого sing-box пишет "no available network interface".
 */
object DefaultNetworkMonitor {
    private const val TAG = "DefaultNetMon"

    @Volatile
    var underlying: Network? = null
        private set

    private var listener: InterfaceUpdateListener? = null
    private var registered = false
    private var cm: ConnectivityManager? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            underlying = network
            notifyListener(network)
        }

        override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
            if (network == underlying) notifyListener(network)
        }

        override fun onLost(network: Network) {
            if (network == underlying) {
                underlying = null
                notifyListener(null)
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
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                connectivity.registerBestMatchingNetworkCallback(request, callback, mainHandler)
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                connectivity.requestNetwork(request, callback, mainHandler)
            } else {
                connectivity.requestNetwork(request, callback)
            }
            registered = true
            // сразу подтянем текущую
            pickInitial(connectivity)
            LogStore.append("network monitor started")
        } catch (e: Exception) {
            Log.e(TAG, "register failed", e)
            LogStore.append("network monitor error: ${e.message}")
            // fallback без callback
            pickInitial(connectivity)
        }
    }

    fun stop() {
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

    private fun pickInitial(connectivity: ConnectivityManager) {
        // Ищем сеть с интернетом, но не VPN
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
        if (network == null) {
            runCatching { updateListener.updateDefaultInterface("", -1, false, false) }
            return
        }
        // Несколько попыток — linkProperties появляются с задержкой
        Thread {
            repeat(15) { attempt ->
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
                        }
                        return@Thread
                    }
                }
                Thread.sleep(100)
            }
            LogStore.append("default iface: failed to resolve")
            runCatching { updateListener.updateDefaultInterface("", -1, false, false) }
        }.start()
    }
}
