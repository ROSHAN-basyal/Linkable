package com.linkable.notifications

import java.util.concurrent.ConcurrentHashMap

data class ActiveAppCall(
    val notificationId: String,
    val packageName: String,
    val appName: String,
    val title: String,
    val body: String,
    val callStateHint: String,
    val updatedAtMs: Long,
)

object AppCallActivityTracker {
    private val activeCalls = ConcurrentHashMap<String, ActiveAppCall>()
    @Volatile
    private var lastAppCallSeenAtMs: Long = 0L

    fun recordPosted(
        notificationId: String,
        packageName: String,
        appName: String,
        title: String,
        body: String,
        callStateHint: String,
    ) {
        val now = System.currentTimeMillis()
        lastAppCallSeenAtMs = now
        activeCalls[notificationId] = ActiveAppCall(
            notificationId = notificationId,
            packageName = packageName,
            appName = appName,
            title = title,
            body = body,
            callStateHint = callStateHint,
            updatedAtMs = now,
        )
    }

    fun recordRemoved(notificationId: String) {
        if (activeCalls.remove(notificationId) != null) {
            lastAppCallSeenAtMs = System.currentTimeMillis()
        }
    }

    fun activeRecent(maxAgeMs: Long = ACTIVE_CALL_MAX_AGE_MS): ActiveAppCall? {
        val now = System.currentTimeMillis()
        prune(now, maxAgeMs)
        return activeCalls.values.maxByOrNull { it.updatedAtMs }
    }

    fun recentlySawAppCall(maxAgeMs: Long = RECENT_CALL_WINDOW_MS): Boolean {
        return System.currentTimeMillis() - lastAppCallSeenAtMs <= maxAgeMs
    }

    private fun prune(now: Long, maxAgeMs: Long) {
        activeCalls.entries.removeIf { (_, call) -> now - call.updatedAtMs > maxAgeMs }
    }

    private const val ACTIVE_CALL_MAX_AGE_MS = 2L * 60L * 1_000L
    private const val RECENT_CALL_WINDOW_MS = 15L * 1_000L
}
