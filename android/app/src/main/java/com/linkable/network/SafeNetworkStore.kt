package com.linkable.network

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.util.Base64
import androidx.core.content.ContextCompat
import com.linkable.debug.DebugEventLog
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest

data class SafeWifiNetwork(
    val fingerprint: String,
    val label: String,
    val enabled: Boolean = true,
)

data class SafeWifiPolicySnapshot(
    val allowAllWifi: Boolean,
    val locationPermissionGranted: Boolean,
    val currentWifiLabel: String,
    val networks: List<SafeWifiNetwork>,
)

class SafeNetworkStore(context: Context) {
    private val appContext = context.applicationContext
    private val preferences = appContext.getSharedPreferences("linkable_safe_networks", Context.MODE_PRIVATE)
    private val connectivityManager = appContext.getSystemService(ConnectivityManager::class.java)
    private val wifiManager = appContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val lock = Any()

    fun snapshot(): SafeWifiPolicySnapshot {
        return SafeWifiPolicySnapshot(
            allowAllWifi = allowAllWifi(),
            locationPermissionGranted = hasLocationPermission(),
            currentWifiLabel = currentWifiNetwork()?.label.orEmpty(),
            networks = allKnownNetworks(),
        )
    }

    fun allowAllWifi(): Boolean {
        return preferences.getBoolean(KEY_ALLOW_ALL_WIFI, false)
    }

    fun setAllowAllWifi(allowAll: Boolean) {
        if (allowAllWifi() == allowAll) {
            return
        }
        preferences.edit().putBoolean(KEY_ALLOW_ALL_WIFI, allowAll).apply()
        DebugEventLog.record(
            "network",
            if (allowAll) "Safe Wi-Fi restriction disabled; pairing is allowed on all Wi-Fi." else "Safe Wi-Fi restriction enabled.",
        )
    }

    fun currentWifiNetwork(): SafeWifiNetwork? {
        val activeNetwork = connectivityManager.activeNetwork ?: return null
        val capabilities = connectivityManager.getNetworkCapabilities(activeNetwork) ?: return null
        if (!capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) return null
        if (!hasLocationPermission()) {
            return null
        }

        @Suppress("DEPRECATION")
        val info = wifiManager.connectionInfo ?: return null
        val ssid = info.ssid.cleanWifiField()
        if (ssid.isBlank() || ssid == UNKNOWN_SSID) return null
        // The SSID is the network-level safe-list key. BSSID changes across mesh/AP roaming,
        // while the paired desktop identity still protects the encrypted Linkable session.
        val stableMaterial = ssid
        val digest = MessageDigest.getInstance("SHA-256").digest(stableMaterial.toByteArray(Charsets.UTF_8))
        return SafeWifiNetwork(
            fingerprint = Base64.encodeToString(digest, Base64.NO_WRAP),
            label = ssid,
        )
    }

    fun isCurrentNetworkTrusted(deviceId: String): Boolean {
        if (allowAllWifi()) return true
        val current = currentWifiNetwork() ?: return false
        return networksFor(deviceId).any { it.fingerprint == current.fingerprint && it.enabled }
    }

    fun trustCurrentNetwork(deviceId: String, deviceName: String, requireCurrent: Boolean = true): Boolean {
        val current = currentWifiNetwork()
        if (current == null) {
            if (requireCurrent) {
                DebugEventLog.record(
                    "network",
                    "Cannot safe-list Wi-Fi for $deviceName; grant Location permission and keep Wi-Fi connected.",
                )
            }
            return false
        }
        synchronized(lock) {
            val all = readAll().toMutableMap()
            val networks = all[deviceId].orEmpty().associateBy { it.fingerprint }.toMutableMap()
            val existing = networks[current.fingerprint]
            if (existing?.enabled == true) {
                return true
            }
            networks[current.fingerprint] = current
            all[deviceId] = networks.values.sortedBy { it.label.lowercase() }
            writeAll(all)
        }
        DebugEventLog.record("network", "Safe-listed Wi-Fi ${current.label} for $deviceName")
        return true
    }

    fun setNetworkEnabled(fingerprint: String, enabled: Boolean) {
        val changed = synchronized(lock) {
            var updatedAny = false
            val all = readAll().mapValues { (_, networks) ->
                networks.map { network ->
                    if (network.fingerprint == fingerprint && network.enabled != enabled) {
                        updatedAny = true
                        network.copy(enabled = enabled)
                    } else {
                        network
                    }
                }
            }
            if (updatedAny) {
                writeAll(all)
            }
            updatedAny
        }
        if (!changed) {
            return
        }
        DebugEventLog.record("network", "Safe Wi-Fi ${if (enabled) "enabled" else "disabled"} for stored network.")
    }

    fun removeDevice(deviceId: String) {
        val removed = synchronized(lock) {
            val all = readAll().toMutableMap()
            if (all.remove(deviceId) == null) {
                false
            } else {
                writeAll(all)
                true
            }
        }
        if (removed) {
            DebugEventLog.record("network", "Removed Safe Wi-Fi entries for forgotten device.")
        }
    }

    fun labelsFor(deviceId: String): List<String> {
        return networksFor(deviceId).map { it.label }
    }

    private fun allKnownNetworks(): List<SafeWifiNetwork> {
        return readAll()
            .values
            .flatten()
            .associateBy { it.fingerprint }
            .values
            .sortedBy { it.label.lowercase() }
    }

    private fun networksFor(deviceId: String): List<SafeWifiNetwork> {
        return readAll()[deviceId].orEmpty()
    }

    private fun readAll(): Map<String, List<SafeWifiNetwork>> {
        val raw = preferences.getString(KEY_NETWORKS, null) ?: return emptyMap()
        return runCatching {
            val root = JSONObject(raw)
            buildMap {
                root.keys().forEach { deviceId ->
                    val array = root.getJSONArray(deviceId)
                    val networks = buildList {
                        for (index in 0 until array.length()) {
                            val item = array.getJSONObject(index)
                            add(
                                SafeWifiNetwork(
                                    fingerprint = item.getString("fingerprint"),
                                    label = item.getString("label"),
                                    enabled = item.optBoolean("enabled", true),
                                ),
                            )
                        }
                    }
                    put(deviceId, networks)
                }
            }
        }.getOrDefault(emptyMap())
    }

    private fun writeAll(networksByDevice: Map<String, List<SafeWifiNetwork>>) {
        val root = JSONObject()
        networksByDevice.toSortedMap().forEach { (deviceId, networks) ->
            val array = JSONArray()
            networks.forEach { network ->
                array.put(
                        JSONObject()
                            .put("fingerprint", network.fingerprint)
                            .put("label", network.label)
                            .put("enabled", network.enabled),
                )
            }
            root.put(deviceId, array)
        }
        preferences.edit().putString(KEY_NETWORKS, root.toString()).apply()
    }

    private fun String?.cleanWifiField(): String {
        val raw = this?.trim().orEmpty()
        return raw.removeSurrounding("\"")
    }

    private fun hasLocationPermission(): Boolean {
        return ContextCompat.checkSelfPermission(appContext, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
    }

    companion object {
        private const val KEY_ALLOW_ALL_WIFI = "allow_all_wifi"
        private const val KEY_NETWORKS = "safe_networks_by_device"
        private const val UNKNOWN_SSID = "<unknown ssid>"
    }
}
