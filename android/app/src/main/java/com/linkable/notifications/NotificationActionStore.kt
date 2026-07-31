package com.linkable.notifications

import android.app.Notification
import android.app.PendingIntent
import android.app.RemoteInput
import android.content.Context
import android.content.Intent
import com.linkable.protocol.v1.NotificationActionRequest
import com.linkable.protocol.v1.NotificationActionResult
import com.linkable.protocol.v1.NotificationReplyRequest
import com.linkable.protocol.v1.NotificationReplyResult
import com.linkable.protocol.v1.Timestamp
import java.util.concurrent.ConcurrentHashMap

data class StoredNotificationAction(
    val title: String,
    val actionIntent: PendingIntent?,
    val remoteInputs: Array<RemoteInput>,
)

object NotificationActionStore {
    private val actionsByNotification = ConcurrentHashMap<String, Map<String, StoredNotificationAction>>()

    fun put(notificationId: String, notification: Notification) {
        val normalActions = notification.actions.orEmpty()
            .mapIndexed { index, action ->
                index.toString() to StoredNotificationAction(
                    title = action.title?.toString().orEmpty(),
                    actionIntent = action.actionIntent,
                    remoteInputs = action.remoteInputs.orEmpty().map { it }.toTypedArray(),
                )
            }
        val callStyleActions = listOfNotNull(
            notification.callStylePendingIntent(Notification.EXTRA_ANSWER_INTENT)?.let {
                CALL_STYLE_ANSWER_ACTION_ID to StoredNotificationAction("Answer", it, emptyArray())
            },
            notification.callStylePendingIntent(Notification.EXTRA_DECLINE_INTENT)?.let {
                CALL_STYLE_DECLINE_ACTION_ID to StoredNotificationAction("Decline", it, emptyArray())
            },
            notification.callStylePendingIntent(Notification.EXTRA_HANG_UP_INTENT)?.let {
                CALL_STYLE_HANG_UP_ACTION_ID to StoredNotificationAction("Hang up", it, emptyArray())
            },
        )
        actionsByNotification[notificationId] = (normalActions + callStyleActions).toMap()
    }

    fun remove(notificationId: String) {
        actionsByNotification.remove(notificationId)
    }

    fun executeReply(context: Context, request: NotificationReplyRequest): NotificationReplyResult {
        val resultBuilder = NotificationReplyResult.newBuilder()
            .setRequestId(request.requestId)
            .setNotificationId(request.notificationId)
            .setActionId(request.actionId)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())

        val action = actionsByNotification[request.notificationId]?.get(request.actionId)
            ?: return resultBuilder
                .setSuccess(false)
                .setDetail("notification action is no longer available")
                .build()
        val actionIntent = action.actionIntent
            ?: return resultBuilder
                .setSuccess(false)
                .setDetail("notification action has no pending intent")
                .build()
        if (action.remoteInputs.isEmpty()) {
            return resultBuilder
                .setSuccess(false)
                .setDetail("notification action does not support remote input")
                .build()
        }

        return runCatching {
            val intent = Intent()
            val results = android.os.Bundle()
            action.remoteInputs.forEach { remoteInput ->
                results.putCharSequence(remoteInput.resultKey, request.replyText)
            }
            RemoteInput.addResultsToIntent(action.remoteInputs, intent, results)
            actionIntent.send(context, 0, intent)
            resultBuilder
                .setSuccess(true)
                .setDetail("reply sent through ${action.title.ifBlank { "notification action" }}")
                .build()
        }.getOrElse { error ->
            resultBuilder
                .setSuccess(false)
                .setDetail(error.message ?: error.javaClass.simpleName)
                .build()
        }
    }

    fun executeAction(context: Context, request: NotificationActionRequest): NotificationActionResult {
        val resultBuilder = NotificationActionResult.newBuilder()
            .setRequestId(request.requestId)
            .setNotificationId(request.notificationId)
            .setActionId(request.actionId)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())

        val action = actionsByNotification[request.notificationId]?.get(request.actionId)
            ?: return resultBuilder
                .setSuccess(false)
                .setDetail("notification action is no longer available")
                .build()
        val actionIntent = action.actionIntent
            ?: return resultBuilder
                .setSuccess(false)
                .setDetail("notification action has no pending intent")
                .build()

        return runCatching {
            sendPlainAction(context, actionIntent)
            val lowerTitle = action.title.lowercase()
            if (
                lowerTitle.contains("decline") ||
                lowerTitle.contains("reject") ||
                lowerTitle.contains("hang") ||
                lowerTitle.contains("end") ||
                lowerTitle.contains("leave") ||
                lowerTitle.contains("ignore")
            ) {
                remove(request.notificationId)
            }
            resultBuilder
                .setSuccess(true)
                .setDetail("action sent through ${action.title.ifBlank { "notification action" }}")
                .build()
        }.getOrElse { error ->
            resultBuilder
                .setSuccess(false)
                .setDetail(error.message ?: error.javaClass.simpleName)
                .build()
        }
    }

    @Suppress("DEPRECATION")
    private fun Notification.callStylePendingIntent(key: String): PendingIntent? {
        return extras.getParcelable(key)
    }

    private fun sendPlainAction(context: Context, actionIntent: PendingIntent) {
        runCatching {
            actionIntent.send()
        }.getOrElse {
            actionIntent.send(context, 0, Intent())
        }
    }

    const val CALL_STYLE_ANSWER_ACTION_ID = "__callstyle_answer__"
    const val CALL_STYLE_DECLINE_ACTION_ID = "__callstyle_decline__"
    const val CALL_STYLE_HANG_UP_ACTION_ID = "__callstyle_hangup__"
}
