package com.linkable.notifications

import com.linkable.protocol.v1.NotificationPosted
import com.linkable.protocol.v1.NotificationRemoved
import com.linkable.transport.SessionEventSignal
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel

sealed interface PhoneNotificationEvent {
    data class Posted(val notification: NotificationPosted) : PhoneNotificationEvent
    data class Removed(val notification: NotificationRemoved) : PhoneNotificationEvent
}

object NotificationBridge {
    val events = Channel<PhoneNotificationEvent>(
        capacity = 256,
        onBufferOverflow = BufferOverflow.DROP_OLDEST,
    )

    fun publish(event: PhoneNotificationEvent) {
        if (events.trySend(event).isSuccess) {
            SessionEventSignal.notifyPendingWork()
        }
    }
}
