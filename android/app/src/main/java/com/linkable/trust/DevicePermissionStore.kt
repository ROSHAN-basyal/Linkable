package com.linkable.trust

import android.content.Context
import org.json.JSONObject

data class DevicePermissions(
    val notifications: Boolean = true,
    val files: Boolean = false,
    val fileBrowse: Boolean = false,
    val calls: Boolean = false,
    val contacts: Boolean = false,
    val sharedApps: Boolean = false,
    val cameraShare: Boolean = true,
    val forwardClipboardToPc: Boolean = false,
    val pcControl: Boolean = false,
)

class DevicePermissionStore(context: Context) {
    private val preferences = context.getSharedPreferences("linkable_device_permissions", Context.MODE_PRIVATE)
    private val lock = Any()
    private val cache = mutableMapOf<String, DevicePermissions>()

    init {
        migrateDefaultsIfNeeded()
    }

    fun permissionsFor(deviceId: String): DevicePermissions = synchronized(lock) {
        cache.getOrPut(deviceId) { readPermissions(deviceId) }
    }

    private fun readPermissions(deviceId: String): DevicePermissions {
        val raw = preferences.getString(deviceId, null) ?: return DevicePermissions()
        val json = runCatching { JSONObject(raw) }.getOrNull() ?: return DevicePermissions()
        val defaults = DevicePermissions()
        return DevicePermissions(
            notifications = json.optBoolean("notifications", defaults.notifications),
            files = json.optBoolean("files", defaults.files),
            fileBrowse = json.optBoolean("file_browse", defaults.fileBrowse),
            calls = json.optBoolean("calls", defaults.calls),
            contacts = json.optBoolean("contacts", defaults.contacts),
            sharedApps = json.optBoolean("shared_apps", defaults.sharedApps),
            cameraShare = json.optBoolean("camera_share", defaults.cameraShare),
            forwardClipboardToPc = json.optBoolean("forward_clipboard_to_pc", defaults.forwardClipboardToPc),
            pcControl = json.optBoolean("pc_control", defaults.pcControl),
        )
    }

    fun setPermission(deviceId: String, key: PermissionKey, enabled: Boolean) {
        synchronized(lock) {
            val current = cache.getOrPut(deviceId) { readPermissions(deviceId) }
            val updated = when (key) {
                PermissionKey.NOTIFICATIONS -> current.copy(notifications = enabled)
                PermissionKey.FILES -> current.copy(files = enabled)
                PermissionKey.FILE_BROWSE -> current.copy(fileBrowse = enabled)
                PermissionKey.CALLS -> current.copy(calls = enabled)
                PermissionKey.CONTACTS -> current.copy(contacts = enabled)
                PermissionKey.SHARED_APPS -> current.copy(sharedApps = enabled)
                PermissionKey.CAMERA_SHARE -> current.copy(cameraShare = enabled)
                PermissionKey.FORWARD_CLIPBOARD_TO_PC -> current.copy(forwardClipboardToPc = enabled)
                PermissionKey.PC_CONTROL -> current.copy(pcControl = enabled)
            }
            cache[deviceId] = updated
            preferences.edit().putString(deviceId, updated.toJson().toString()).apply()
        }
    }

    fun remove(deviceId: String) {
        synchronized(lock) {
            cache.remove(deviceId)
            preferences.edit().remove(deviceId).apply()
        }
    }

    private fun DevicePermissions.toJson(): JSONObject {
        return JSONObject()
            .put("notifications", notifications)
            .put("files", files)
            .put("file_browse", fileBrowse)
            .put("calls", calls)
            .put("contacts", contacts)
            .put("shared_apps", sharedApps)
            .put("camera_share", cameraShare)
            .put("forward_clipboard_to_pc", forwardClipboardToPc)
            .put("pc_control", pcControl)
    }

    private fun migrateDefaultsIfNeeded() {
        if (preferences.getInt(KEY_SCHEMA_VERSION, 0) >= SCHEMA_VERSION) return
        val editor = preferences.edit()
        preferences.all.forEach { (key, value) ->
            if (key == KEY_SCHEMA_VERSION) return@forEach
            val raw = value as? String ?: return@forEach
            val json = runCatching { JSONObject(raw) }.getOrNull() ?: return@forEach

            // Older builds had no visible global notification permission toggle, but stored
            // notifications=false when any other per-device setting was changed.
            json.put("notifications", true)
            json.remove("clipboard_laptop_to_mobile")
            json.remove("clipboard_mobile_to_laptop")
            if (!json.has("forward_clipboard_to_pc")) {
                json.put("forward_clipboard_to_pc", false)
            }
            editor.putString(key, json.toString())
        }
        editor.putInt(KEY_SCHEMA_VERSION, SCHEMA_VERSION).apply()
    }

    private companion object {
        const val KEY_SCHEMA_VERSION = "__schema_version"
        const val SCHEMA_VERSION = 3
    }
}

enum class PermissionKey {
    NOTIFICATIONS,
    FILES,
    FILE_BROWSE,
    CALLS,
    CONTACTS,
    SHARED_APPS,
    CAMERA_SHARE,
    FORWARD_CLIPBOARD_TO_PC,
    PC_CONTROL,
}
