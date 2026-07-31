package com.linkable.pairing

sealed interface PairingState {
    data object Idle : PairingState
    data class Connecting(val deviceName: String) : PairingState
    data class AwaitingCodeEntry(val deviceName: String, val code: String) : PairingState
    data class PairingInProgress(val deviceName: String) : PairingState
    data class Success(
        val deviceName: String,
        val deviceId: String,
        val reusedTrust: Boolean = false,
        val transportSummary: String? = null,
    ) : PairingState
    data class Reconnecting(val deviceName: String, val attempt: Int, val detail: String) : PairingState
    data class Error(val message: String) : PairingState
}
