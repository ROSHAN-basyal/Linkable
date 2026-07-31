package com.linkable.crypto

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PublicKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec

data class LocalPeerDescriptor(
    val deviceId: String,
    val deviceName: String,
    val publicKeyBytes: ByteArray,
)

class DeviceIdentity(
    private val alias: String,
    val deviceName: String,
) {
    private val keyStore: KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    init {
        ensureKeyPair()
    }

    val publicKeyBytes: ByteArray
        get() = keyStore.getCertificate(alias).publicKey.encoded

    val deviceId: String
        get() = CryptoUtils.deriveDeviceId(publicKeyBytes)

    fun localDescriptor(): LocalPeerDescriptor = LocalPeerDescriptor(
        deviceId = deviceId,
        deviceName = deviceName,
        publicKeyBytes = publicKeyBytes,
    )

    fun sign(payload: ByteArray): ByteArray {
        val privateKey = keyStore.getKey(alias, null)
        val signature = Signature.getInstance("SHA256withECDSA")
        signature.initSign(privateKey as java.security.PrivateKey)
        signature.update(payload)
        return signature.sign()
    }

    companion object {
        fun verify(publicKeyBytes: ByteArray, payload: ByteArray, signatureBytes: ByteArray): Boolean {
            val publicKey = publicKeyFromBytes(publicKeyBytes)
            val signature = Signature.getInstance("SHA256withECDSA")
            signature.initVerify(publicKey)
            signature.update(payload)
            return signature.verify(signatureBytes)
        }

        fun publicKeyFromBytes(publicKeyBytes: ByteArray): PublicKey {
            val factory = KeyFactory.getInstance("EC")
            return factory.generatePublic(X509EncodedKeySpec(publicKeyBytes))
        }
    }

    private fun ensureKeyPair() {
        if (keyStore.containsAlias(alias)) {
            return
        }
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        val spec = KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY,
        )
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .build()
        generator.initialize(spec)
        generator.generateKeyPair()
    }
}

