package com.linkable.discovery

enum class DiscoverySource {
    NSD,
    DIRECT_CONNECT,
}

data class DiscoveredDevice(
    val serviceName: String,
    val deviceName: String,
    val host: String,
    val port: Int,
    val protocolVersion: String = "unknown",
    val deviceId: String = "unknown",
    val source: DiscoverySource = DiscoverySource.NSD,
) {
    val endpoint: String
        get() = "$host:$port"
}

