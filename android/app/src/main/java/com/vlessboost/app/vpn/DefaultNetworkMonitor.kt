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

/**
 * Следит за реальной сетью (Wi‑Fi/LTE), исключая VPN, и отдаёт её в
 * [VpnService.Builder.setUnderlyingNetworks].
 *
 * Важно (Wi‑Fi crash 1.1.7):
 * - НЕ вызываем InterfaceUpdateListener.updateDefaultInterface / Libbox.updateDefaultInterface.
 *   На Wi‑Fi (wlan0 + rmnet одновременно, IPv4+IPv6) нативный путь в libbox убивал процесс;
 *   на cellular тот же путь обычно жил. Cellular/Wi‑Fi outbound держим через
 *   setUnderlyingNetworks + VpnService.protect().
 * - Callback'и только обновляют [underlying]; Go iface push отключён навсегда.
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

    private val callback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            if (isVpnNetwork(network)) return
            adopt(network, "onAvailable")
        }

        override fun onCapabilitiesChanged(network: Network, networkCapabilities: NetworkCapabilities) {
            if (networkCapabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) return
            if (network == underlying) {
                logTransport(network, "capsChanged")
            } else if (networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) {
                // Prefer validated default when callback fires for a better match.
                adopt(network, "capsChanged")
            }
        }

        override fun onLost(network: Network) {
            if (network != underlying) return
            underlying = null
            LogStore.append("default network lost")
            val connectivity = cm
            if (connectivity != null) {
                pickInitial(connectivity)
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
            LogStore.append("network monitor started (no Go updateDefaultInterface)")
        } catch (e: Exception) {
            Log.e(TAG, "register failed", e)
            LogStore.append("network monitor error: ${e.message}")
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

    /**
     * Раньше включал push в Go после openTun. Теперь no-op: updateDefaultInterface
     * на Wi‑Fi крашил процесс; underlying Network и так выставляется в openTun.
     */
    fun setUpdatesEnabled(enabled: Boolean) {
        LogStore.append("network monitor updatesEnabled=$enabled (Go iface push disabled)")
        if (enabled) {
            underlying?.let { logTransport(it, "armed") }
        }
    }

    fun setListener(updateListener: InterfaceUpdateListener?) {
        listener = updateListener
        LogStore.append(
            "network monitor listener=${if (updateListener != null) "set" else "cleared"} " +
                "(updateDefaultInterface no-op)",
        )
        // Намеренно НЕ вызываем updateListener.updateDefaultInterface — Wi‑Fi killer.
    }

    private fun isVpnNetwork(network: Network): Boolean {
        val caps = cm?.getNetworkCapabilities(network) ?: return false
        return caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
    }

    private fun adopt(network: Network, reason: String) {
        underlying = network
        logTransport(network, reason)
    }

    private fun pickInitial(connectivity: ConnectivityManager) {
        // 1) Активная validated default (не VPN)
        val active = connectivity.activeNetwork
        if (active != null) {
            val caps = connectivity.getNetworkCapabilities(active)
            if (caps != null &&
                caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
                !caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
            ) {
                adopt(active, "activeNetwork")
                return
            }
        }
        // 2) Первая validated non-VPN с INTERNET
        var fallback: Network? = null
        for (network in connectivity.allNetworks) {
            val caps = connectivity.getNetworkCapabilities(network) ?: continue
            if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) continue
            if (caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) continue
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M &&
                caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
            ) {
                adopt(network, "validated")
                return
            }
            if (fallback == null) fallback = network
        }
        fallback?.let { adopt(it, "fallback") }
    }

    private fun logTransport(network: Network, reason: String) {
        val caps = cm?.getNetworkCapabilities(network)
        val transport = when {
            caps == null -> "UNKNOWN"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WIFI"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "CELLULAR"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ETHERNET"
            else -> "OTHER"
        }
        val name = runCatching {
            cm?.getLinkProperties(network)?.interfaceName
        }.getOrNull().orEmpty()
        LogStore.append(
            "default network transport=$transport iface=${name.ifBlank { "?" }} reason=$reason",
        )
    }
}
