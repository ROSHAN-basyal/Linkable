package com.linkable.calls

import android.Manifest
import android.os.Bundle
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.telecom.PhoneAccountHandle
import android.telecom.TelecomManager
import android.telephony.SubscriptionInfo
import android.telephony.SubscriptionManager
import androidx.core.content.ContextCompat
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.DialRequest
import com.linkable.protocol.v1.DialResult
import com.linkable.protocol.v1.Timestamp

class DialHandler(
    context: Context,
) {
    private val appContext = context.applicationContext
    private val telecomManager = appContext.getSystemService(TelecomManager::class.java)
    private val subscriptionManager = appContext.getSystemService(SubscriptionManager::class.java)

    fun handle(request: DialRequest): DialResult {
        val phoneNumber = sanitizeNumber(request.phoneNumber)
        if (phoneNumber.isBlank()) {
            return result(request, success = false, detail = "phone number is empty")
        }
        if (request.directCall && !hasCallPhonePermission()) {
            return result(request, success = false, detail = "CALL_PHONE permission missing")
        }

        val simSlot = request.simSlot.takeIf { it > 0 } ?: 1
        val resolvedSubscription = resolveSubscription(simSlot)
        val resolvedHandle = resolvedSubscription?.let { resolvePhoneAccountHandle(it.subscriptionId) }
        val detail = runCatching {
            CallSessionContext.recordOutgoingDial(phoneNumber, simSlot, resolvedSubscription)
            if (request.directCall) {
                placeCall(phoneNumber, simSlot, resolvedSubscription, resolvedHandle)
            } else {
                startDialer(phoneNumber, simSlot, resolvedSubscription, resolvedHandle)
            }
            buildString {
                append(if (request.directCall) "telecom placeCall requested" else "dialer intent started")
                append("; requested SIM $simSlot")
                if (resolvedSubscription != null) {
                    append("; resolved subscription ${resolvedSubscription.subscriptionId}")
                } else {
                    append("; SIM $simSlot not resolved, system default may be used")
                }
                if (resolvedHandle != null) {
                    append("; phone account selected")
                }
            }
        }.getOrElse { error ->
            CallSessionContext.clearOutgoing()
            "dial failed: ${error.message}"
        }

        val success = !detail.startsWith("dial failed")
        DebugEventLog.record("call", detail)
        return result(
            request = request,
            success = success,
            detail = detail,
            resolvedSubscription = resolvedSubscription,
        )
    }

    private fun sanitizeNumber(number: String): String {
        return number.filter { it.isDigit() || it == '+' || it == '*' || it == '#' || it == ',' || it == ';' }
    }

    private fun resolveSubscription(simSlotOneBased: Int): SubscriptionInfo? {
        if (!hasPhoneStatePermission()) return null
        val slotIndex = simSlotOneBased - 1
        return runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                subscriptionManager.getActiveSubscriptionInfoForSimSlotIndex(slotIndex)
            } else {
                @Suppress("DEPRECATION")
                subscriptionManager.activeSubscriptionInfoList?.firstOrNull { it.simSlotIndex == slotIndex }
            }
        }.getOrNull()
    }

    private fun resolvePhoneAccountHandle(subscriptionId: Int): PhoneAccountHandle? {
        if (!hasPhoneStatePermission()) return null
        val subId = subscriptionId.toString()
        return runCatching {
            telecomManager.callCapablePhoneAccounts.firstOrNull { handle ->
                handle.id == subId || handle.id.contains(subId)
            }
        }.getOrNull()
    }

    private fun placeCall(
        phoneNumber: String,
        simSlot: Int,
        subscription: SubscriptionInfo?,
        handle: PhoneAccountHandle?,
    ) {
        val extras = Bundle().apply {
            handle?.let { putParcelable(TelecomManager.EXTRA_PHONE_ACCOUNT_HANDLE, it) }
            addSubscriptionHints(simSlot, subscription)
        }
        telecomManager.placeCall(Uri.parse("tel:${Uri.encode(phoneNumber)}"), extras)
    }

    private fun startDialer(
        phoneNumber: String,
        simSlot: Int,
        subscription: SubscriptionInfo?,
        handle: PhoneAccountHandle?,
    ) {
        val intent = Intent(Intent.ACTION_DIAL).apply {
            data = Uri.parse("tel:${Uri.encode(phoneNumber)}")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
            handle?.let { putExtra(TelecomManager.EXTRA_PHONE_ACCOUNT_HANDLE, it) }
            addSubscriptionHints(simSlot, subscription)
        }
        appContext.startActivity(intent)
    }

    private fun Intent.addSubscriptionHints(simSlot: Int, subscription: SubscriptionInfo?) {
        putExtra("com.android.phone.extra.slot", simSlot - 1)
        putExtra("slot", simSlot - 1)
        putExtra("simSlot", simSlot - 1)
        subscription?.let {
            putExtra("subscription", it.subscriptionId)
            putExtra("Subscription", it.subscriptionId)
            putExtra("android.telephony.extra.SUBSCRIPTION_INDEX", it.subscriptionId)
        }
    }

    private fun Bundle.addSubscriptionHints(simSlot: Int, subscription: SubscriptionInfo?) {
        putInt("com.android.phone.extra.slot", simSlot - 1)
        putInt("slot", simSlot - 1)
        putInt("simSlot", simSlot - 1)
        subscription?.let {
            putInt("subscription", it.subscriptionId)
            putInt("Subscription", it.subscriptionId)
            putInt("android.telephony.extra.SUBSCRIPTION_INDEX", it.subscriptionId)
        }
    }

    private fun hasCallPhonePermission(): Boolean {
        return ContextCompat.checkSelfPermission(appContext, Manifest.permission.CALL_PHONE) == PackageManager.PERMISSION_GRANTED
    }

    private fun hasPhoneStatePermission(): Boolean {
        return ContextCompat.checkSelfPermission(appContext, Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED
    }

    private fun result(
        request: DialRequest,
        success: Boolean,
        detail: String,
        resolvedSubscription: SubscriptionInfo? = null,
    ): DialResult {
        return DialResult.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(success)
            .setDetail(detail)
            .setRequestedSimSlot(request.simSlot.takeIf { it > 0 } ?: 1)
            .setRequestedSimResolved(resolvedSubscription != null)
            .setResolvedSubscriptionId(resolvedSubscription?.subscriptionId ?: -1)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }
}
