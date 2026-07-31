package com.linkable.calls

import com.linkable.protocol.v1.CallMetadataEvent
import com.linkable.protocol.v1.CallStateEvent
import com.linkable.transport.SessionEventSignal
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel

object CallStateBridge {
    val events = Channel<CallStateEvent>(capacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)
    val metadataEvents = Channel<CallMetadataEvent>(capacity = 8, onBufferOverflow = BufferOverflow.DROP_OLDEST)

    fun publish(event: CallStateEvent) {
        if (events.trySend(event).isSuccess) {
            SessionEventSignal.notifyPendingWork()
        }
    }

    fun publishMetadata(event: CallMetadataEvent) {
        if (metadataEvents.trySend(event).isSuccess) {
            SessionEventSignal.notifyPendingWork()
        }
    }
}
