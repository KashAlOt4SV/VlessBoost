package com.vlessboost.app.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager.NameNotFoundException
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import androidx.core.app.NotificationCompat
import com.vlessboost.app.LogStore
import com.vlessboost.app.MainActivity
import com.vlessboost.app.Prefs
import com.vlessboost.app.Presets
import com.vlessboost.app.R
import com.vlessboost.app.SingBoxConfigBuilder
import com.vlessboost.app.VlessParser
import go.Seq
import io.nekohasekai.libbox.BridgeOptions
import io.nekohasekai.libbox.BridgeSession
import io.nekohasekai.libbox.CommandClient
import io.nekohasekai.libbox.CommandClientHandler
import io.nekohasekai.libbox.CommandClientOptions
import io.nekohasekai.libbox.CommandServer
import io.nekohasekai.libbox.CommandServerHandler
import io.nekohasekai.libbox.ConnectionEvents
import io.nekohasekai.libbox.ConnectionOwner
import io.nekohasekai.libbox.DnsQuery
import io.nekohasekai.libbox.InterfaceUpdateListener
import io.nekohasekai.libbox.Libbox
import io.nekohasekai.libbox.LocalDNSTransport
import io.nekohasekai.libbox.LogIterator
import io.nekohasekai.libbox.NeighborUpdateListener
import io.nekohasekai.libbox.NetworkInterface
import io.nekohasekai.libbox.NetworkInterfaceIterator
import io.nekohasekai.libbox.OutboundGroupItemIterator
import io.nekohasekai.libbox.OutboundGroupIterator
import io.nekohasekai.libbox.OverrideOptions
import io.nekohasekai.libbox.PlatformInterface
import io.nekohasekai.libbox.PlatformUser
import io.nekohasekai.libbox.ShellSession
import io.nekohasekai.libbox.StatusMessage
import io.nekohasekai.libbox.StringIterator
import io.nekohasekai.libbox.SystemProxyStatus
import io.nekohasekai.libbox.TunOptions
import io.nekohasekai.libbox.WIFIState
import io.nekohasekai.libbox.Notification as LibboxNotification
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class BoostVpnService : VpnService(), PlatformInterface, CommandServerHandler {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var commandServer: CommandServer? = null
    private var commandClient: CommandClient? = null
    private var tunPfd: ParcelFileDescriptor? = null
    @Volatile
    private var starting = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopBoost()
                return START_NOT_STICKY
            }
        }
        startForeground(NOTIFY_ID, buildNotification(getString(R.string.status_starting)))
        if (starting || isRunning) return START_STICKY
        starting = true
        scope.launch {
            try {
                startBoost()
                broadcastStatus(true)
                updateNotification(getString(R.string.status_on))
            } catch (e: Exception) {
                Log.e(TAG, "start failed", e)
                LogStore.append("ERROR: ${e.message}")
                broadcastError(e.message ?: e.toString())
                stopBoost()
            } finally {
                starting = false
            }
        }
        return START_STICKY
    }

    private suspend fun startBoost() = withContext(Dispatchers.IO) {
        val prefs = Prefs(this@BoostVpnService)
        val url = prefs.vlessUrl.trim()
        require(url.isNotBlank()) { "Нет VLESS ссылки" }
        val packages = prefs.selectedApps.toList()
        require(packages.isNotEmpty()) { "Не выбрано ни одного приложения" }
        val domains = prefs.selectedPresets
            .flatMap { id -> Presets.all.find { it.id == id }?.domains.orEmpty() }
            .distinct()
        val endpoint = VlessParser.parse(url)
        val config = SingBoxConfigBuilder.build(endpoint, packages, domains)
        LogStore.append("start: apps=${packages.joinToString()}")
        LogStore.append("start: server=${endpoint.server}:${endpoint.port} security=${endpoint.security} net=${endpoint.network}")
        LogStore.append("start: domains=${domains.size}")
        LogStore.append("config:\n${config.take(4000)}")
        Log.i(TAG, "config ready, apps=${packages.size}, domains=${domains.size}")

        Seq.touch()
        Libbox.touch()

        DefaultNetworkMonitor.setUpdatesEnabled(false)
        DefaultNetworkMonitor.start(this@BoostVpnService)

        stopLogClient()
        runCatching { commandServer?.closeService() }
        runCatching { commandServer?.close() }

        val server = CommandServer(this@BoostVpnService, this@BoostVpnService)
        server.start()
        commandServer = server
        LogStore.append("command server started")

        // include_package уже в JSON-конфиге — не дублируем через OverrideOptions
        // (иначе TunOptions отдаёт пакеты дважды: packages=2N).
        val override = OverrideOptions().apply {
            autoRedirect = false
        }
        LogStore.append("calling startOrReloadService…")
        server.startOrReloadService(config, override)
        LogStore.append("service started / reloaded (after openTun)")
        isRunning = true
        // Только теперь пушим default iface в Go — иначе гонка с openTun убивает процесс.
        DefaultNetworkMonitor.setUpdatesEnabled(true)
        LogStore.append("post-start: monitor updates armed")
        delay(300)
        startLogClient()
        LogStore.append("post-start: log client done, still alive")
    }

    private fun startLogClient() {
        try {
            val opts = CommandClientOptions().apply {
                addCommand(Libbox.CommandLog)
            }
            val client = Libbox.newCommandClient(logClientHandler, opts)
            client.connect()
            commandClient = client
            LogStore.append("log client connected")
        } catch (e: Exception) {
            LogStore.append("log client error: ${e.message}")
            Log.w(TAG, "log client", e)
        }
    }

    private fun stopLogClient() {
        runCatching { commandClient?.disconnect() }
        commandClient = null
    }

    private val logClientHandler = object : CommandClientHandler {
        override fun connected() {
            LogStore.append("client: connected")
        }

        override fun disconnected(message: String?) {
            LogStore.append("client: disconnected ${message.orEmpty()}")
        }

        override fun clearLogs() {}

        override fun writeLogs(logs: LogIterator?) {
            if (logs == null) return
            while (logs.hasNext()) {
                val entry = logs.next()
                LogStore.append(entry.message ?: "")
            }
        }

        override fun writeStatus(message: StatusMessage?) {
            if (message == null) return
            LogStore.append(
                "status up=${message.uplink} down=${message.downlink} mem=${message.memory}",
            )
        }

        override fun writeGroups(groups: OutboundGroupIterator?) {}
        override fun writeOutbounds(outbounds: OutboundGroupItemIterator?) {}
        override fun writeConnectionEvents(events: ConnectionEvents?) {}
        override fun writeDNSQuery(query: DnsQuery?) {}
        override fun initializeClashMode(modes: StringIterator?, current: String?) {}
        override fun updateClashMode(mode: String?) {}
        override fun setDefaultLogLevel(level: Int) {}
    }

    private fun stopBoost() {
        LogStore.append("stopping…")
        stopLogClient()
        runCatching { commandServer?.closeService() }
        runCatching { commandServer?.close() }
        commandServer = null
        runCatching { tunPfd?.close() }
        tunPfd = null
        DefaultNetworkMonitor.stop()
        isRunning = false
        broadcastStatus(false)
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onRevoke() {
        stopBoost()
    }

    override fun onDestroy() {
        scope.cancel()
        if (isRunning) stopBoost()
        super.onDestroy()
    }

    // region CommandServerHandler
    override fun serviceStop() {
        stopBoost()
    }

    override fun serviceReload() {
        scope.launch {
            try {
                startBoost()
            } catch (e: Exception) {
                Log.e(TAG, "reload failed", e)
                broadcastError(e.message ?: e.toString())
                stopBoost()
            }
        }
    }

    override fun getSystemProxyStatus(): SystemProxyStatus =
        SystemProxyStatus().apply {
            available = false
            enabled = false
        }

    override fun setSystemProxyEnabled(isEnabled: Boolean) {}

    override fun triggerNativeCrash() {
        throw RuntimeException("debug crash")
    }

    override fun writeDebugMessage(message: String?) {
        Log.d(TAG, message ?: "")
        if (!message.isNullOrBlank()) LogStore.append(message)
    }

    override fun connectSSHAgent(): Int = -1
    // endregion

    // region PlatformInterface
    override fun openTun(options: TunOptions): Int {
        try {
            if (prepare(this) != null) error("Нет разрешения VPN")

            val builder = Builder()
                .setSession("VLESS Boost")
                .setMtu(options.getMTU())

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                builder.setMetered(false)
            }

            // Физическая сеть под VPN — иначе outbound не знает куда биндиться
            DefaultNetworkMonitor.underlying?.let { net ->
                try {
                    builder.setUnderlyingNetworks(arrayOf(net))
                    LogStore.append("underlying network set")
                } catch (e: Exception) {
                    LogStore.append("setUnderlyingNetworks: ${e.message}")
                }
            }

            val inet4Address = options.inet4Address
            while (inet4Address.hasNext()) {
                val address = inet4Address.next()
                builder.addAddress(address.address(), address.prefix())
            }
            val inet6Address = options.inet6Address
            while (inet6Address.hasNext()) {
                val address = inet6Address.next()
                builder.addAddress(address.address(), address.prefix())
            }

            // VpnService сам добавляет маршруты/DNS. При auto_route=false libbox не
            // отдаёт route list — ставим полный IPv4 default + DNS для hijack.
            var dnsAdded = 0
            if (options.autoRoute) {
                val dnsMode = options.getDNSMode()?.value
                if (dnsMode != null && dnsMode != Libbox.DNSModeDisabled) {
                    val dnsServerAddress = options.getDNSServerAddress()
                    while (dnsServerAddress.hasNext()) {
                        builder.addDnsServer(dnsServerAddress.next())
                        dnsAdded++
                    }
                }

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    val inet4RouteAddress = options.inet4RouteAddress
                    if (inet4RouteAddress.hasNext()) {
                        while (inet4RouteAddress.hasNext()) {
                            val a = inet4RouteAddress.next()
                            builder.addRoute(a.address(), a.prefix())
                        }
                    } else {
                        builder.addRoute("0.0.0.0", 0)
                    }
                    val inet6RouteAddress = options.inet6RouteAddress
                    if (inet6RouteAddress.hasNext()) {
                        while (inet6RouteAddress.hasNext()) {
                            val a = inet6RouteAddress.next()
                            builder.addRoute(a.address(), a.prefix())
                        }
                    }
                } else {
                    val inet4RouteAddress = options.inet4RouteRange
                    if (inet4RouteAddress.hasNext()) {
                        while (inet4RouteAddress.hasNext()) {
                            val a = inet4RouteAddress.next()
                            builder.addRoute(a.address(), a.prefix())
                        }
                    } else {
                        builder.addRoute("0.0.0.0", 0)
                    }
                    val inet6RouteAddress = options.inet6RouteRange
                    if (inet6RouteAddress.hasNext()) {
                        while (inet6RouteAddress.hasNext()) {
                            val a = inet6RouteAddress.next()
                            builder.addRoute(a.address(), a.prefix())
                        }
                    }
                }
            } else {
                builder.addRoute("0.0.0.0", 0)
                builder.addDnsServer("1.1.1.1")
                dnsAdded = 1
            }
            LogStore.append("openTun routes autoRoute=${options.autoRoute} dns=$dnsAdded")

            val allowed = linkedSetOf<String>()
            val includePackage = options.includePackage
            while (includePackage.hasNext()) {
                val pkg = includePackage.next()
                if (pkg.isNullOrBlank() || !allowed.add(pkg)) continue
                try {
                    builder.addAllowedApplication(pkg)
                    Log.d(TAG, "allow $pkg")
                } catch (e: NameNotFoundException) {
                    allowed.remove(pkg)
                    Log.w(TAG, "missing package $pkg")
                    LogStore.append("openTun: missing package $pkg")
                } catch (e: Exception) {
                    allowed.remove(pkg)
                    LogStore.append("openTun: allow $pkg failed: ${e.message}")
                }
            }

            val excludePackage = options.excludePackage
            while (excludePackage.hasNext()) {
                val pkg = excludePackage.next()
                try {
                    builder.addDisallowedApplication(pkg)
                } catch (_: NameNotFoundException) {
                } catch (e: Exception) {
                    LogStore.append("openTun: disallow $pkg failed: ${e.message}")
                }
            }

            if (allowed.isEmpty()) {
                // Fallback: если в TunOptions пусто — берём из Prefs
                Prefs(this).selectedApps.forEach { pkg ->
                    if (!allowed.add(pkg)) return@forEach
                    try {
                        builder.addAllowedApplication(pkg)
                    } catch (_: NameNotFoundException) {
                        allowed.remove(pkg)
                    } catch (e: Exception) {
                        allowed.remove(pkg)
                        LogStore.append("openTun: fallback allow $pkg failed: ${e.message}")
                    }
                }
            }
            if (allowed.isEmpty()) error("Не выбрано ни одного приложения")

            LogStore.append("openTun establish… packages=${allowed.size}")
            val pfd = builder.establish() ?: error("Не удалось создать VPN-интерфейс")
            tunPfd = pfd
            LogStore.append("TUN established fd=${pfd.fd} packages=${allowed.size}")
            return pfd.fd
        } catch (e: Exception) {
            LogStore.append("openTun ERROR: ${e.message}")
            Log.e(TAG, "openTun", e)
            throw e
        }
    }

    override fun autoDetectInterfaceControl(fd: Int) {
        try {
            if (!protect(fd)) {
                LogStore.append("protect($fd)=false")
            }
        } catch (e: Exception) {
            LogStore.append("protect($fd) error: ${e.message}")
            Log.w(TAG, "protect $fd", e)
        }
    }

    override fun usePlatformAutoDetectInterfaceControl(): Boolean = true
    override fun includeAllNetworks(): Boolean = false
    override fun underNetworkExtension(): Boolean = false
    override fun useProcFS(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
    override fun clearDNSCache() {}
    override fun findConnectionOwner(
        ipProtocol: Int,
        sourceAddress: String?,
        sourcePort: Int,
        destinationAddress: String?,
        destinationPort: Int,
    ): ConnectionOwner {
        // Непроброшенные Java-исключения через JNI/gomobile часто убивают процесс без LogStore.
        try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
                error("android: findConnectionOwner requires API 29+")
            }
            val cm = getSystemService(android.net.ConnectivityManager::class.java)
                ?: error("android: ConnectivityManager missing")
            val uid = cm.getConnectionOwnerUid(
                ipProtocol,
                java.net.InetSocketAddress(sourceAddress ?: "", sourcePort),
                java.net.InetSocketAddress(destinationAddress ?: "", destinationPort),
            )
            if (uid == android.os.Process.INVALID_UID) {
                error("android: connection owner not found")
            }
            val packages = packageManager.getPackagesForUid(uid)?.toList().orEmpty()
            return ConnectionOwner().apply {
                userId = uid
                userName = packages.firstOrNull().orEmpty()
                setAndroidPackageNames(StringArray(packages))
            }
        } catch (e: Exception) {
            LogStore.append(
                "findConnectionOwner fail proto=$ipProtocol " +
                    "${sourceAddress ?: "?"}:$sourcePort -> ${destinationAddress ?: "?"}:$destinationPort: ${e.message}",
            )
            throw e
        }
    }

    override fun getInterfaces(): NetworkInterfaceIterator {
        return try {
            val cm = getSystemService(android.net.ConnectivityManager::class.java)
            val javaNifs = java.net.NetworkInterface.getNetworkInterfaces()?.toList().orEmpty()
            val list = mutableListOf<NetworkInterface>()
            if (cm != null) {
                for (network in cm.allNetworks) {
                    val caps = cm.getNetworkCapabilities(network) ?: continue
                    val lp = cm.getLinkProperties(network) ?: continue
                    if (!caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_INTERNET)) continue
                    // Не отдаём сам VPN/tun — иначе auto_detect зациклится
                    if (caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN)) continue
                    val name = lp.interfaceName ?: continue
                    if (name.startsWith("tun") || name.startsWith("ppp") || name.startsWith("wg")) continue
                    val javaNif = javaNifs.find { it.name == name } ?: continue
                    val box = NetworkInterface()
                    box.name = name
                    box.index = javaNif.index
                    box.mtu = runCatching { javaNif.mtu }.getOrDefault(1500)
                    box.type = when {
                        caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI) -> Libbox.InterfaceTypeWIFI
                        caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_CELLULAR) -> Libbox.InterfaceTypeCellular
                        caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_ETHERNET) -> Libbox.InterfaceTypeEthernet
                        else -> Libbox.InterfaceTypeOther
                    }
                    // IFF_UP | IFF_RUNNING
                    box.flags = 0x1 or 0x40
                    val addrs = javaNif.interfaceAddresses.mapNotNull { ia ->
                        val host = ia.address.hostAddress ?: return@mapNotNull null
                        "$host/${ia.networkPrefixLength}"
                    }
                    box.addresses = StringArray(addrs)
                    box.dnsServer = StringArray(lp.dnsServers.mapNotNull { it.hostAddress })
                    box.metered = !caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
                    list.add(box)
                }
            }
            LogStore.append("getInterfaces count=${list.size}: ${list.joinToString { it.name }}")
            object : NetworkInterfaceIterator {
                private val it = list.iterator()
                override fun hasNext(): Boolean = it.hasNext()
                override fun next(): NetworkInterface = it.next()
            }
        } catch (e: Exception) {
            LogStore.append("getInterfaces ERROR: ${e.message}")
            Log.e(TAG, "getInterfaces", e)
            object : NetworkInterfaceIterator {
                override fun hasNext(): Boolean = false
                override fun next(): NetworkInterface = NetworkInterface()
            }
        }
    }

    override fun startDefaultInterfaceMonitor(listener: InterfaceUpdateListener?) {
        LogStore.append("startDefaultInterfaceMonitor")
        try {
            DefaultNetworkMonitor.start(this)
            // Только сохранить listener — updateDefaultInterface после TUN (setUpdatesEnabled).
            DefaultNetworkMonitor.setListener(listener)
        } catch (e: Exception) {
            LogStore.append("startDefaultInterfaceMonitor ERROR: ${e.message}")
            Log.e(TAG, "startDefaultInterfaceMonitor", e)
        }
    }

    override fun closeDefaultInterfaceMonitor(listener: InterfaceUpdateListener?) {
        try {
            DefaultNetworkMonitor.setUpdatesEnabled(false)
            DefaultNetworkMonitor.setListener(null)
        } catch (e: Exception) {
            LogStore.append("closeDefaultInterfaceMonitor ERROR: ${e.message}")
        }
    }
    override fun startNeighborMonitor(listener: NeighborUpdateListener?) {}
    override fun closeNeighborMonitor(listener: NeighborUpdateListener?) {}
    override fun readWIFIState(): WIFIState? = null
    override fun localDNSTransport(): LocalDNSTransport? = null
    override fun sendNotification(notification: LibboxNotification?) {}
    override fun registerMyInterface(name: String?) {}
    override fun usePlatformBridge(): Boolean = false
    override fun createBridge(options: BridgeOptions?): BridgeSession {
        throw UnsupportedOperationException("bridge")
    }
    override fun usePlatformShell(): Boolean = false
    override fun checkPlatformShell() {}
    override fun lookupUser(username: String?): PlatformUser {
        throw UnsupportedOperationException("shell")
    }
    override fun openShellSession(
        user: PlatformUser?,
        command: String?,
        args: StringIterator?,
        workingDirectory: String?,
        uid: Int,
        gid: Int,
    ): ShellSession {
        throw UnsupportedOperationException("shell")
    }
    override fun lookupSFTPServer(): String = ""
    override fun readSystemSSHHostKey(): String = ""
    override fun tailscaleHostname(): String = ""
    // endregion

    private fun buildNotification(text: String): Notification {
        ensureChannel()
        val pi = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setSmallIcon(R.drawable.ic_logo)
            .setContentIntent(pi)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIFY_ID, buildNotification(text))
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "VPN", NotificationManager.IMPORTANCE_LOW),
        )
    }

    private fun broadcastStatus(running: Boolean) {
        sendBroadcast(
            Intent(ACTION_STATUS).setPackage(packageName).putExtra(EXTRA_RUNNING, running),
        )
    }

    private fun broadcastError(message: String) {
        sendBroadcast(
            Intent(ACTION_STATUS).setPackage(packageName)
                .putExtra(EXTRA_RUNNING, false)
                .putExtra(EXTRA_ERROR, message),
        )
    }

    class StringArray(values: Collection<String>) : StringIterator {
        constructor(iterator: Iterator<String>) : this(iterator.asSequence().toList())

        private val items = values.toList()
        private var index = 0

        override fun len(): Int = items.size
        override fun hasNext(): Boolean = index < items.size
        override fun next(): String = items[index++]
    }

    companion object {
        private const val TAG = "BoostVpnService"
        const val ACTION_STOP = "com.vlessboost.app.STOP"
        const val ACTION_STATUS = "com.vlessboost.app.STATUS"
        const val EXTRA_RUNNING = "running"
        const val EXTRA_ERROR = "error"
        private const val CHANNEL_ID = "vpn"
        private const val NOTIFY_ID = 1

        @Volatile
        var isRunning: Boolean = false
            private set

        fun start(context: android.content.Context) {
            val i = Intent(context, BoostVpnService::class.java)
            androidx.core.content.ContextCompat.startForegroundService(context, i)
        }

        fun stop(context: android.content.Context) {
            val i = Intent(context, BoostVpnService::class.java).setAction(ACTION_STOP)
            context.startService(i)
        }
    }
}
