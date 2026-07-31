package com.linkable.calls

import android.telephony.SubscriptionInfo

data class PendingOutgoingCallContext(
    val phoneNumber: String,
    val simSlot: Int,
    val subscriptionId: Int,
    val carrierName: String,
    val createdAtMs: Long = System.currentTimeMillis(),
)

object CallSessionContext {
    private const val MAX_PENDING_AGE_MS = 120_000L

    @Volatile
    private var pendingOutgoing: PendingOutgoingCallContext? = null

    fun recordOutgoingDial(phoneNumber: String, simSlot: Int, subscription: SubscriptionInfo?) {
        pendingOutgoing = PendingOutgoingCallContext(
            phoneNumber = phoneNumber,
            simSlot = simSlot,
            subscriptionId = subscription?.subscriptionId ?: -1,
            carrierName = subscription?.carrierName?.toString().orEmpty(),
        )
    }

    fun currentOutgoing(): PendingOutgoingCallContext? {
        val value = pendingOutgoing ?: return null
        if (System.currentTimeMillis() - value.createdAtMs > MAX_PENDING_AGE_MS) {
            pendingOutgoing = null
            return null
        }
        return value
    }

    fun clearOutgoing() {
        pendingOutgoing = null
    }
}
