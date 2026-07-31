package com.linkable.trust

import android.util.Base64

data class TrustedDevice(
    val deviceId: String,
    val deviceName: String,
    val publicKeyB64: String,
    val pairedAtEpochMs: Long,
) {
    val publicKeyBytes: ByteArray
        get() = Base64.decode(publicKeyB64, Base64.DEFAULT)
}
