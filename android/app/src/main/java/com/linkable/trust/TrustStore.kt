package com.linkable.trust

import android.content.Context
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject

class TrustStore(context: Context) {
    private val preferences = context.getSharedPreferences("linkable_trust_store", Context.MODE_PRIVATE)
    private val lock = Any()
    private val devices = loadRecords().associateBy { it.deviceId }.toMutableMap()

    fun upsert(device: TrustedDevice) {
        synchronized(lock) {
            devices[device.deviceId] = device
            persistLocked()
        }
    }

    fun get(deviceId: String): TrustedDevice? = synchronized(lock) { devices[deviceId] }

    fun listRecords(): List<TrustedDevice> = synchronized(lock) {
        devices.values.sortedBy { it.deviceName.lowercase() }
    }

    fun remove(deviceId: String): Boolean = synchronized(lock) {
        if (devices.remove(deviceId) == null) {
            return@synchronized false
        }
        persistLocked()
        true
    }

    private fun loadRecords(): List<TrustedDevice> {
        val raw = preferences.getString(KEY_DEVICES, null) ?: return emptyList()
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (index in 0 until array.length()) {
                    val item = array.getJSONObject(index)
                    add(
                        TrustedDevice(
                            deviceId = item.getString("device_id"),
                            deviceName = item.getString("device_name"),
                            publicKeyB64 = item.getString("public_key_b64"),
                            pairedAtEpochMs = item.getLong("paired_at_epoch_ms"),
                        ),
                    )
                }
            }
        }.getOrDefault(emptyList())
    }

    private fun persistLocked() {
        val json = JSONArray()
        devices.values.sortedBy { it.deviceName.lowercase() }.forEach { record ->
            json.put(
                JSONObject()
                    .put("device_id", record.deviceId)
                    .put("device_name", record.deviceName)
                    .put("public_key_b64", record.publicKeyB64)
                    .put("paired_at_epoch_ms", record.pairedAtEpochMs),
            )
        }
        preferences.edit().putString(KEY_DEVICES, json.toString()).apply()
    }

    companion object {
        private const val KEY_DEVICES = "trusted_devices"

        fun trustedDeviceFromPublicKey(
            deviceId: String,
            deviceName: String,
            publicKeyBytes: ByteArray,
            pairedAtEpochMs: Long,
        ): TrustedDevice = TrustedDevice(
            deviceId = deviceId,
            deviceName = deviceName,
            publicKeyB64 = Base64.encodeToString(publicKeyBytes, Base64.NO_WRAP),
            pairedAtEpochMs = pairedAtEpochMs,
        )
    }
}
