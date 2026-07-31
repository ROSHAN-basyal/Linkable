package com.linkable.transport

import kotlinx.coroutines.channels.Channel

/**
 * Wakes the active encrypted-session writer when any producer queues work.
 *
 * The signal is conflated because queue contents hold the actual events; one
 * pending wake-up is enough regardless of how many producers fire together.
 */
object SessionEventSignal {
    val events = Channel<Unit>(Channel.CONFLATED)

    fun notifyPendingWork() {
        events.trySend(Unit)
    }
}
