package com.vlessboost.app

import android.net.Uri
import org.json.JSONArray
import org.json.JSONObject

data class VlessEndpoint(
    val uuid: String,
    val server: String,
    val port: Int,
    val flow: String = "",
    val network: String = "tcp",
    val security: String = "none",
    val sni: String = "",
    val fingerprint: String = "",
    val publicKey: String = "",
    val shortId: String = "",
    val spiderX: String = "",
    val path: String = "",
    val host: String = "",
    val name: String = "vless",
)

object VlessParser {
    fun parse(raw: String): VlessEndpoint {
        val text = raw.trim()
        require(text.startsWith("vless://", ignoreCase = true)) { "Ссылка должна начинаться с vless://" }
        val uri = Uri.parse(text)
        val uuid = Uri.decode(uri.userInfo ?: "")
        val server = uri.host ?: ""
        val port = if (uri.port != -1) uri.port else 443
        require(uuid.isNotBlank() && server.isNotBlank()) { "Некорректная VLESS ссылка" }

        fun q(key: String, default: String = ""): String =
            uri.getQueryParameter(key) ?: default

        return VlessEndpoint(
            uuid = uuid,
            server = server,
            port = port,
            flow = q("flow"),
            network = q("type", "tcp"),
            security = q("security", "none"),
            sni = q("sni"),
            fingerprint = q("fp").ifBlank { q("fingerprint") },
            publicKey = q("pbk").ifBlank { q("publicKey") },
            shortId = q("sid").ifBlank { q("shortId") },
            spiderX = Uri.decode(q("spx").ifBlank { q("spiderX") }),
            path = Uri.decode(q("path")),
            host = q("host"),
            name = Uri.decode(uri.fragment ?: "vless"),
        )
    }
}

object SingBoxConfigBuilder {
    fun build(
        endpoint: VlessEndpoint,
        packages: Collection<String>,
        domains: Collection<String>,
    ): String {
        val proxy = JSONObject().apply {
            put("type", "vless")
            put("tag", "proxy")
            put("server", endpoint.server)
            put("server_port", endpoint.port)
            put("uuid", endpoint.uuid)
            if (endpoint.flow.isNotBlank()) put("flow", endpoint.flow)
            put("packet_encoding", "xudp")

            val security = endpoint.security.lowercase()
            if (security == "tls" || security == "reality") {
                val tls = JSONObject().apply {
                    put("enabled", true)
                    put("server_name", endpoint.sni.ifBlank { endpoint.host.ifBlank { endpoint.server } })
                    if (endpoint.fingerprint.isNotBlank()) {
                        put("utls", JSONObject().put("enabled", true).put("fingerprint", endpoint.fingerprint))
                    }
                    if (security == "reality") {
                        require(endpoint.publicKey.isNotBlank()) { "Для Reality нужен pbk" }
                        put(
                            "reality",
                            JSONObject()
                                .put("enabled", true)
                                .put("public_key", endpoint.publicKey)
                                .put("short_id", endpoint.shortId),
                        )
                    }
                }
                put("tls", tls)
            }

            when (endpoint.network.lowercase()) {
                "ws" -> put(
                    "transport",
                    JSONObject().put("type", "ws").put("path", endpoint.path.ifBlank { "/" }).also {
                        if (endpoint.host.isNotBlank()) {
                            it.put("headers", JSONObject().put("Host", endpoint.host))
                        }
                    },
                )
                "grpc" -> put("transport", JSONObject().put("type", "grpc").put("service_name", endpoint.host))
            }
        }

        val rules = JSONArray().apply {
            put(JSONObject().put("action", "sniff"))
            put(JSONObject().put("protocol", "dns").put("action", "hijack-dns"))
            put(
                JSONObject()
                    .put("ip_is_private", true)
                    .put("action", "route")
                    .put("outbound", "direct"),
            )
            // Весь трафик выбранных приложений уже в TUN → в proxy
            if (packages.isNotEmpty()) {
                put(JSONObject().put("action", "route").put("outbound", "proxy"))
            } else if (domains.isNotEmpty()) {
                put(
                    JSONObject()
                        .put("domain_suffix", JSONArray(domains.toList()))
                        .put("action", "route")
                        .put("outbound", "proxy"),
                )
            }
        }

        val tun = JSONObject().apply {
            put("type", "tun")
            put("tag", "tun-in")
            put("address", JSONArray().put("172.19.0.1/30"))
            put("mtu", 9000)
            put("auto_route", true)
            put("strict_route", false)
            // system stack стабильнее на Android VpnService
            put("stack", "system")
            put("endpoint_independent_nat", true)
            if (packages.isNotEmpty()) {
                put("include_package", JSONArray(packages.toList()))
            }
        }

        val root = JSONObject().apply {
            put("log", JSONObject().put("level", "info").put("timestamp", true))
            // DNS выбранных приложений тоже через proxy — иначе часто «висит»
            put(
                "dns",
                JSONObject()
                    .put(
                        "servers",
                        JSONArray()
                            .put(
                                JSONObject()
                                    .put("type", "https")
                                    .put("tag", "dns-remote")
                                    .put("server", "1.1.1.1")
                                    .put("detour", "proxy"),
                            )
                            .put(
                                JSONObject()
                                    .put("type", "udp")
                                    .put("tag", "dns-direct")
                                    .put("server", "8.8.8.8"),
                            ),
                    )
                    .put("final", if (packages.isNotEmpty()) "dns-remote" else "dns-direct")
                    .put("strategy", "ipv4_only")
                    .put("independent_cache", true),
            )
            put("inbounds", JSONArray().put(tun))
            put(
                "outbounds",
                JSONArray()
                    .put(proxy)
                    .put(JSONObject().put("type", "direct").put("tag", "direct")),
            )
            put(
                "route",
                JSONObject()
                    .put("auto_detect_interface", true)
                    .put("default_domain_resolver", if (packages.isNotEmpty()) "dns-remote" else "dns-direct")
                    .put("rules", rules)
                    .put("final", if (packages.isNotEmpty()) "proxy" else "direct"),
            )
        }
        return root.toString(2)
    }
}
