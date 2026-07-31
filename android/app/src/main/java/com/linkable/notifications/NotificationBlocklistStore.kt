package com.linkable.notifications

import android.content.Context

class NotificationBlocklistStore(context: Context) {
    private val preferences = context.getSharedPreferences("linkable_notification_blocklist", Context.MODE_PRIVATE)

    fun isBlocked(deviceId: String, packageName: String): Boolean {
        return preferences.getBoolean(key(deviceId, packageName), false)
    }

    fun setBlocked(deviceId: String, packageName: String, blocked: Boolean) {
        preferences.edit().putBoolean(key(deviceId, packageName), blocked).apply()
    }

    fun removeDevice(deviceId: String) {
        val prefix = "${deviceId.ifBlank { "global" }}::"
        val editor = preferences.edit()
        preferences.all.keys
            .filter { it.startsWith(prefix) }
            .forEach { editor.remove(it) }
        editor.apply()
    }

    private fun key(deviceId: String, packageName: String): String {
        return "${deviceId.ifBlank { "global" }}::$packageName"
    }
}
