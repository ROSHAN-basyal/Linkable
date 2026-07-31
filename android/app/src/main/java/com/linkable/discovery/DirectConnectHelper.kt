package com.linkable.discovery

data class DirectConnectCandidate(
    val host: String,
    val port: Int,
) {
    val endpoint: String
        get() = "$host:$port"

    fun toDevice(deviceName: String = "Direct Connect Candidate"): DiscoveredDevice =
        DiscoveredDevice(
            serviceName = "direct://$endpoint",
            deviceName = deviceName,
            host = host,
            port = port,
            protocolVersion = "manual",
            deviceId = "unverified",
            source = DiscoverySource.DIRECT_CONNECT,
        )
}

object DirectConnectHelper {
    fun parse(input: String, defaultPort: Int = 37891): Result<DirectConnectCandidate> = runCatching {
        val trimmed = input.trim()
        require(trimmed.isNotEmpty()) { "Endpoint is empty" }

        if (trimmed.startsWith("[") && trimmed.contains("]")) {
            val end = trimmed.indexOf(']')
            val host = trimmed.substring(1, end)
            val tail = trimmed.substring(end + 1)
            val port = if (tail.startsWith(":")) tail.drop(1).toInt() else defaultPort
            return@runCatching DirectConnectCandidate(host = host, port = port)
        }

        val parts = trimmed.split(":")
        if (parts.size == 2 && parts[0].isNotBlank() && parts[1].isNotBlank()) {
            return@runCatching DirectConnectCandidate(host = parts[0], port = parts[1].toInt())
        }

        DirectConnectCandidate(host = trimmed, port = defaultPort)
    }
}
