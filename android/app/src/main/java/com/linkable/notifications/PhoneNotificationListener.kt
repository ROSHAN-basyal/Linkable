package com.linkable.notifications

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.NotificationListenerService.Ranking
import android.service.notification.NotificationListenerService.RankingMap
import android.service.notification.StatusBarNotification
import com.linkable.debug.DebugEventLog
import com.google.protobuf.ByteString
import com.linkable.protocol.v1.NotificationAction
import com.linkable.protocol.v1.NotificationActionSemantic
import com.linkable.protocol.v1.NotificationPosted
import com.linkable.protocol.v1.NotificationRemoved
import com.linkable.protocol.v1.Timestamp
import com.linkable.service.LinkableForegroundService
import java.io.ByteArrayOutputStream
import java.util.Locale
import java.security.MessageDigest

class PhoneNotificationListener : NotificationListenerService() {
    private val forwardedNotificationIds = mutableSetOf<String>()
    private val forwardedCallNotificationIds = mutableSetOf<String>()
    private val forwardedActiveCallNotificationIds = mutableSetOf<String>()
    private val forwardedNotificationFingerprints = mutableMapOf<String, String>()
    private val forwardingHistory: SharedPreferences by lazy {
        getSharedPreferences("linkable_forwarded_notification_history", Context.MODE_PRIVATE)
    }
    private var lastHistoryPruneAtMs = 0L

    override fun onListenerConnected() {
        super.onListenerConnected()
        runCatching {
            LinkableForegroundService.start(this)
        }.onFailure { error ->
            DebugEventLog.record("service", "Notification listener could not start LAN service: ${error.message}")
        }
        runCatching {
            activeNotifications.orEmpty().forEach { sbn ->
                handleNotificationPosted(sbn, currentRanking)
            }
        }.onFailure { error ->
            DebugEventLog.record("notification-filter", "Active notification sync failed: ${error.message}")
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        handleNotificationPosted(sbn, currentRanking)
    }

    override fun onNotificationPosted(sbn: StatusBarNotification, rankingMap: RankingMap) {
        handleNotificationPosted(sbn, rankingMap)
    }

    private fun handleNotificationPosted(sbn: StatusBarNotification, rankingMap: RankingMap?) {
        if (sbn.packageName == packageName) return
        val notification = sbn.notification ?: return
        val notificationId = stableNotificationId(sbn)
        val actions = notificationActions(notification)
        val title = notification.extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty()
        val body = notification.extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty()
        val callLike = isCallLikeNotification(sbn.packageName, notification, title, body, actions)
        val visibility = forwardingDecision(
            sbn = sbn,
            notification = notification,
            rankingMap = rankingMap,
            title = title,
            body = body,
            callLike = callLike,
        )
        if (!visibility.forward) {
            NotificationActionStore.remove(notificationId)
            val wasCallLike = forwardedCallNotificationIds.remove(notificationId)
            if (wasCallLike) {
                AppCallActivityTracker.recordRemoved(notificationId)
            }
            forwardedNotificationIds.remove(notificationId)
            forwardedActiveCallNotificationIds.remove(notificationId)
            forwardedNotificationFingerprints.remove(notificationId)
            if (wasCallLike) {
                publishRemoved(sbn, notificationId)
            }
            DebugEventLog.record(
                "notification-filter",
                "Filtered ${sbn.packageName}: ${visibility.reason}; title=$title; category=${notification.category}; " +
                    "channel=${notification.channelId}",
            )
            return
        }
        val fingerprint = notificationFingerprint(
            sbn = sbn,
            notification = notification,
            title = title,
            body = body,
            actions = actions,
        )
        if (callLike && isThirdPartyCallingApp(sbn.packageName)) {
            AppCallActivityTracker.recordPosted(
                notificationId = notificationId,
                packageName = sbn.packageName,
                appName = appLabel(sbn.packageName),
                title = title,
                body = body,
                callStateHint = callStateHint(notification, actions),
            )
        } else {
            AppCallActivityTracker.recordRemoved(notificationId)
        }
        if (alreadyForwardedRecently(notificationId, fingerprint)) {
            DebugEventLog.record("notification-filter", "Deduped ${sbn.packageName}: title=$title")
            return
        }
        val callStateHint = callStateHint(notification, actions)
        if (callLike && callStateHint == CALL_STATE_ACTIVE) {
            if (notificationId in forwardedActiveCallNotificationIds) {
                DebugEventLog.record("notification-filter", "Deduped ongoing call ${sbn.packageName}: title=$title")
                return
            }
            forwardedActiveCallNotificationIds.add(notificationId)
        }
        val iconPng = appIconPng(sbn.packageName)
        NotificationActionStore.put(notificationId, notification)
        forwardedNotificationIds.add(notificationId)
        if (callLike) {
            forwardedCallNotificationIds.add(notificationId)
        } else {
            forwardedCallNotificationIds.remove(notificationId)
        }
        forwardedNotificationFingerprints[notificationId] = fingerprint
        markForwarded(notificationId, fingerprint)
        if (callLike) {
            DebugEventLog.record(
                "notification",
                "Call-like ${sbn.packageName}: title=$title body=$body category=${notification.category} " +
                    "channel=${notification.channelId} ${visibility.reason} " +
                    "actions=${actions.joinToString { "${it.actionId}:${it.title}:${it.semantic}" }}",
            )
        }
        NotificationBridge.publish(
            PhoneNotificationEvent.Posted(
                NotificationPosted.newBuilder()
                    .setNotificationId(notificationId)
                    .setPackageName(sbn.packageName)
                    .setAppName(appLabel(sbn.packageName))
                    .setTitle(title)
                    .setBody(body)
                    .setChannelId(notification.channelId.orEmpty())
                    .setCategory(notification.category.orEmpty())
                    .setOngoing(notification.flags and Notification.FLAG_ONGOING_EVENT != 0)
                    .setSilent(visibility.silent)
                    .setPostedAt(Timestamp.newBuilder().setUnixEpochMs(sbn.postTime).build())
                    .addAllActions(actions)
                    .setCallLike(callLike)
                    .setCallStateHint(callStateHint)
                    .setAppIconPng(ByteString.copyFrom(iconPng))
                    .setAppIconMime(if (iconPng.isNotEmpty()) "image/png" else "")
                    .build(),
            ),
        )
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        if (sbn.packageName == packageName) return
        val notificationId = stableNotificationId(sbn)
        NotificationActionStore.remove(notificationId)
        forwardedNotificationFingerprints.remove(notificationId)
        val wasCallLike = forwardedCallNotificationIds.remove(notificationId)
        if (wasCallLike) {
            AppCallActivityTracker.recordRemoved(notificationId)
        }
        forwardedNotificationIds.remove(notificationId)
        forwardedActiveCallNotificationIds.remove(notificationId)
        if (wasCallLike) {
            publishRemoved(sbn, notificationId)
        }
    }

    private fun publishRemoved(sbn: StatusBarNotification, notificationId: String) {
        NotificationBridge.publish(
            PhoneNotificationEvent.Removed(
                NotificationRemoved.newBuilder()
                    .setNotificationId(notificationId)
                    .setPackageName(sbn.packageName)
                    .setRemovedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
                    .build(),
            ),
        )
    }

    private fun forwardingDecision(
        sbn: StatusBarNotification,
        notification: Notification,
        rankingMap: RankingMap?,
        title: String,
        body: String,
        callLike: Boolean,
    ): NotificationForwardingDecision {
        val ranking = Ranking()
        val hasRanking = rankingMap?.getRanking(sbn.key, ranking) == true
        val importance = if (hasRanking) ranking.importance else NotificationManager.IMPORTANCE_DEFAULT
        val ambient = hasRanking && ranking.isAmbient
        val category = notification.category.orEmpty()
        val flags = notification.flags
        val ageMs = System.currentTimeMillis() - sbn.postTime

        if (sbn.postTime > 0 && ageMs > MAX_FORWARDING_AGE_MS) {
            return NotificationForwardingDecision.drop("older than 30 minutes ageMs=$ageMs")
        }

        if (callLike) {
            return NotificationForwardingDecision(
                forward = true,
                silent = false,
                reason = "call-like notification allowed; importance=$importance",
            )
        }
        if (flags and Notification.FLAG_GROUP_SUMMARY != 0) {
            return NotificationForwardingDecision.drop("group summary")
        }
        if (flags and Notification.FLAG_FOREGROUND_SERVICE != 0) {
            return NotificationForwardingDecision.drop("foreground service")
        }
        if (flags and Notification.FLAG_ONGOING_EVENT != 0) {
            return NotificationForwardingDecision.drop("ongoing event")
        }
        if (flags and Notification.FLAG_NO_CLEAR != 0) {
            return NotificationForwardingDecision.drop("persistent/no-clear notification")
        }
        if (notificationIsSilent(notification)) {
            return NotificationForwardingDecision.drop("explicitly silent notification")
        }
        if (category in filteredSystemCategories) {
            return NotificationForwardingDecision.drop("system/status/progress category=$category")
        }
        if (isStatusBarUtilityNotification(sbn.packageName, notification, title, body)) {
            return NotificationForwardingDecision.drop("status/date utility notification")
        }
        if (importance < NotificationManager.IMPORTANCE_DEFAULT || ambient) {
            return NotificationForwardingDecision.drop("silent/low-importance notification importance=$importance ambient=$ambient")
        }
        if (title.isBlank() && body.isBlank()) {
            return NotificationForwardingDecision.drop("empty visible text")
        }
        return NotificationForwardingDecision(
            forward = true,
            silent = false,
            reason = "visible notification importance=$importance ambient=$ambient",
        )
    }

    private fun notificationActions(notification: Notification): List<NotificationAction> {
        val normalActions = notification.actions.orEmpty().mapIndexed { index, action ->
            val title = action.title?.toString().orEmpty()
            val supportsRemoteInput = !action.remoteInputs.isNullOrEmpty()
            val nativeSemanticAction = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                action.semanticAction
            } else {
                Notification.Action.SEMANTIC_ACTION_NONE
            }
            NotificationAction.newBuilder()
                .setActionId(index.toString())
                .setTitle(title)
                .setSupportsRemoteInput(supportsRemoteInput)
                .setSupportsPlainIntent(action.actionIntent != null && !supportsRemoteInput)
                .setSemantic(actionSemantic(title, supportsRemoteInput, nativeSemanticAction))
                .build()
        }
        val callStyleActions = listOfNotNull(
            notification.callStylePendingIntent(Notification.EXTRA_ANSWER_INTENT)?.let {
                syntheticCallAction(
                    actionId = NotificationActionStore.CALL_STYLE_ANSWER_ACTION_ID,
                    title = "Answer",
                    semantic = NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL,
                )
            },
            notification.callStylePendingIntent(Notification.EXTRA_DECLINE_INTENT)?.let {
                syntheticCallAction(
                    actionId = NotificationActionStore.CALL_STYLE_DECLINE_ACTION_ID,
                    title = "Decline",
                    semantic = NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL,
                )
            },
            notification.callStylePendingIntent(Notification.EXTRA_HANG_UP_INTENT)?.let {
                syntheticCallAction(
                    actionId = NotificationActionStore.CALL_STYLE_HANG_UP_ACTION_ID,
                    title = "Hang up",
                    semantic = NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL,
                )
            },
        )
        return normalActions + callStyleActions
    }

    private fun syntheticCallAction(
        actionId: String,
        title: String,
        semantic: NotificationActionSemantic,
    ): NotificationAction {
        return NotificationAction.newBuilder()
            .setActionId(actionId)
            .setTitle(title)
            .setSupportsPlainIntent(true)
            .setSemantic(semantic)
            .build()
    }

    private fun actionSemantic(
        title: String,
        supportsRemoteInput: Boolean,
        nativeSemanticAction: Int,
    ): NotificationActionSemantic {
        val normalized = title.normalized()
        return when {
            nativeSemanticAction == Notification.Action.SEMANTIC_ACTION_REPLY -> {
                NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_REPLY
            }
            supportsRemoteInput -> NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_REPLY
            normalized.hasAny("answer", "accept", "pick up", "join", "resume") -> {
                NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL
            }
            normalized.hasAny("decline", "reject", "dismiss", "ignore") -> {
                NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL
            }
            normalized.hasAny("hang up", "hangup", "end call", "end", "leave") -> {
                NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL
            }
            normalized.hasAny("open", "view") -> NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_OPEN
            else -> NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_UNSPECIFIED
        }
    }

    private fun isCallLikeNotification(
        packageName: String,
        notification: Notification,
        title: String,
        body: String,
        actions: List<NotificationAction>,
    ): Boolean {
        if (notification.category == Notification.CATEGORY_CALL) return true
        if (actions.any { it.isCallAction() }) return true
        if (notification.fullScreenIntent != null && packageName in knownCallingPackages) return true
        if (hasCallStyleExtras(notification)) return true
        val searchable = listOf(packageName, notification.channelId.orEmpty(), title, body)
            .joinToString(" ")
            .normalized()
        val knownCallingApp = packageName in knownCallingPackages
        val callWords = searchable.hasAny(
            "incoming call",
            "incoming audio",
            "incoming video",
            "voice call",
            "audio call",
            "video call",
            "phone call",
            "call from",
            "is calling",
            "calling",
            "ringing",
            "missed call",
            "video chat",
            "voice chat",
            "call",
        )
        return knownCallingApp && callWords
    }

    private fun hasCallStyleExtras(notification: Notification): Boolean {
        return notification.callStylePendingIntent(Notification.EXTRA_ANSWER_INTENT) != null ||
            notification.callStylePendingIntent(Notification.EXTRA_DECLINE_INTENT) != null ||
            notification.callStylePendingIntent(Notification.EXTRA_HANG_UP_INTENT) != null ||
            notification.extras.containsKey("android.callPerson")
    }

    private fun isThirdPartyCallingApp(packageName: String): Boolean {
        return packageName in knownCallingPackages
    }

    private fun callStateHint(notification: Notification, actions: List<NotificationAction>): String {
        val hasAnswer = actions.any {
            it.semantic == NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL
        }
        val hasHangup = actions.any {
            it.semantic == NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL
        }
        return when {
            hasAnswer -> CALL_STATE_INCOMING
            hasHangup || (notification.flags and Notification.FLAG_ONGOING_EVENT) != 0 -> CALL_STATE_ACTIVE
            else -> "call-like"
        }
    }

    private fun NotificationAction.isCallAction(): Boolean {
        return semantic == NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL ||
            semantic == NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL ||
            semantic == NotificationActionSemantic.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL
    }

    private fun String.normalized(): String = lowercase(Locale.ROOT)

    private fun String.hasAny(vararg needles: String): Boolean = needles.any { contains(it) }

    private fun isStatusBarUtilityNotification(
        packageName: String,
        notification: Notification,
        title: String,
        body: String,
    ): Boolean {
        val normalizedPackage = packageName.normalized()
        val searchable = listOf(normalizedPackage, notification.channelId.orEmpty(), title, body)
            .joinToString(" ")
            .normalized()
        if (normalizedPackage in dateStatusPackages && searchable.hasAny("patro", "nepali date", "date bar", "status bar", "मिति", "पात्रो")) {
            return true
        }
        return searchable.hasAny("nepali date bar", "date status bar", "persistent date")
    }

    private fun notificationIsSilent(notification: Notification): Boolean {
        val extraSilent = notification.extras.getBoolean("android.silent", false)
        if (extraSilent) return true
        return false
    }

    private fun notificationFingerprint(
        sbn: StatusBarNotification,
        notification: Notification,
        title: String,
        body: String,
        actions: List<NotificationAction>,
    ): String {
        val bigText = notification.extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty()
        val subText = notification.extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString().orEmpty()
        val lines = notification.extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES)
            ?.joinToString("\n") { it.toString() }
            .orEmpty()
        return listOf(
            sbn.packageName,
            sbn.id.toString(),
            sbn.tag.orEmpty(),
            notification.channelId.orEmpty(),
            notification.category.orEmpty(),
            (notification.flags and forwardedFingerprintFlags).toString(),
            title,
            body,
            bigText,
            subText,
            lines,
            actions.joinToString("|") { "${it.actionId}:${it.title}:${it.semantic}:${it.supportsRemoteInput}:${it.supportsPlainIntent}" },
        ).joinToString("\u001f")
    }

    private fun alreadyForwardedRecently(notificationId: String, fingerprint: String): Boolean {
        if (forwardedNotificationFingerprints[notificationId] == fingerprint) {
            return true
        }
        val now = System.currentTimeMillis()
        pruneForwardingHistory(now)
        val historyKey = notificationHistoryKey(notificationId)
        val previousFingerprint = forwardingHistory.getString("$historyKey:fingerprint", null)
        val forwardedAt = forwardingHistory.getLong("$historyKey:time", 0L)
        return previousFingerprint == fingerprint && now - forwardedAt <= MAX_FORWARDING_AGE_MS
    }

    private fun markForwarded(notificationId: String, fingerprint: String) {
        val historyKey = notificationHistoryKey(notificationId)
        forwardingHistory.edit()
            .putString("$historyKey:fingerprint", fingerprint)
            .putLong("$historyKey:time", System.currentTimeMillis())
            .apply()
    }

    private fun pruneForwardingHistory(now: Long) {
        if (now - lastHistoryPruneAtMs < HISTORY_PRUNE_INTERVAL_MS) return
        lastHistoryPruneAtMs = now
        val editor = forwardingHistory.edit()
        forwardingHistory.all.forEach { (key, value) ->
            if (!key.endsWith(":time")) return@forEach
            val timestamp = value as? Long ?: return@forEach
            if (now - timestamp > MAX_FORWARDING_AGE_MS) {
                val prefix = key.removeSuffix(":time")
                editor.remove("$prefix:time")
                editor.remove("$prefix:fingerprint")
            }
        }
        editor.apply()
    }

    private fun notificationHistoryKey(notificationId: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(notificationId.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
    }

    @Suppress("DEPRECATION")
    private fun Notification.callStylePendingIntent(key: String): PendingIntent? {
        return extras.getParcelable(key)
    }

    private fun stableNotificationId(sbn: StatusBarNotification): String {
        return listOf(sbn.packageName, sbn.id.toString(), sbn.tag.orEmpty(), sbn.key).joinToString(":")
    }

    private fun appLabel(packageName: String): String {
        return runCatching {
            val info = packageManager.getApplicationInfo(packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        }.getOrDefault(packageName)
    }

    private fun appIconPng(packageName: String): ByteArray {
        return runCatching {
            val drawable = packageManager.getApplicationIcon(packageName)
            drawable.toPngBytes(sizePx = 96)
        }.getOrDefault(ByteArray(0))
    }

    private fun Drawable.toPngBytes(sizePx: Int): ByteArray {
        val bitmap = when (this) {
            is BitmapDrawable -> bitmap
            else -> Bitmap.createBitmap(
                intrinsicWidth.takeIf { it > 0 } ?: sizePx,
                intrinsicHeight.takeIf { it > 0 } ?: sizePx,
                Bitmap.Config.ARGB_8888,
            ).also { target ->
                val canvas = Canvas(target)
                setBounds(0, 0, canvas.width, canvas.height)
                draw(canvas)
            }
        }
        val scaled = Bitmap.createScaledBitmap(bitmap, sizePx, sizePx, true)
        return ByteArrayOutputStream().use { output ->
            scaled.compress(Bitmap.CompressFormat.PNG, 90, output)
            output.toByteArray()
        }
    }

    private companion object {
        val filteredSystemCategories = setOf(
            Notification.CATEGORY_PROGRESS,
            Notification.CATEGORY_SERVICE,
            Notification.CATEGORY_STATUS,
            Notification.CATEGORY_SYSTEM,
        )

        val knownCallingPackages = setOf(
            "com.whatsapp",
            "com.whatsapp.w4b",
            "com.facebook.orca",
            "com.facebook.katana",
            "com.facebook.lite",
            "com.facebook.mlite",
            "com.instagram.android",
            "org.telegram.messenger",
            "org.thoughtcrime.securesms",
            "com.google.android.apps.meetings",
            "com.google.android.apps.tachyon",
            "us.zoom.videomeetings",
            "com.discord",
            "com.skype.raider",
            "com.viber.voip",
        )

        val dateStatusPackages = setOf(
            "com.hamropatro",
            "com.hamropatro.android",
        )

        const val MAX_FORWARDING_AGE_MS = 30L * 60L * 1_000L
        const val HISTORY_PRUNE_INTERVAL_MS = 10L * 60L * 1_000L
        const val CALL_STATE_INCOMING = "incoming"
        const val CALL_STATE_ACTIVE = "active"
        const val forwardedFingerprintFlags = Notification.FLAG_ONGOING_EVENT or
            Notification.FLAG_FOREGROUND_SERVICE or
            Notification.FLAG_GROUP_SUMMARY or
            Notification.FLAG_NO_CLEAR
    }
}

private data class NotificationForwardingDecision(
    val forward: Boolean,
    val silent: Boolean,
    val reason: String,
) {
    companion object {
        fun drop(reason: String): NotificationForwardingDecision {
            return NotificationForwardingDecision(forward = false, silent = true, reason = reason)
        }
    }
}
