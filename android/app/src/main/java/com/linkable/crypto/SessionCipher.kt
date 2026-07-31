package com.linkable.crypto

import java.nio.ByteBuffer
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

data class EphemeralKeyPair(
    val privateKey: PrivateKey,
    val publicKeyBytes: ByteArray,
)

data class DirectionalSessionKeys(
    val clientToServer: ByteArray,
    val serverToClient: ByteArray,
)

class ReplayGuard {
    private val seen = mutableSetOf<Long>()

    fun checkAndMark(counter: Long) {
        require(seen.add(counter)) { "Replayed encrypted frame counter: $counter" }
    }
}

object SessionCipher {
    private const val SESSION_KEY_SALT_LABEL = "linkable-session-keys-v1"
    private const val CLIENT_TO_SERVER_INFO = "linkable-c2s-v1"
    private const val SERVER_TO_CLIENT_INFO = "linkable-s2c-v1"

    fun generateEphemeralKeyPair(): EphemeralKeyPair {
        val generator = KeyPairGenerator.getInstance("EC")
        generator.initialize(ECGenParameterSpec("secp256r1"))
        val keyPair: KeyPair = generator.generateKeyPair()
        return EphemeralKeyPair(privateKey = keyPair.private, publicKeyBytes = keyPair.public.encoded)
    }

    fun deriveDirectionalKeys(
        privateKey: PrivateKey,
        peerPublicKeyBytes: ByteArray,
        initiatorPublicKeyBytes: ByteArray,
        acceptorPublicKeyBytes: ByteArray,
    ): DirectionalSessionKeys {
        val peerPublicKey = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(peerPublicKeyBytes))
        val agreement = KeyAgreement.getInstance("ECDH")
        agreement.init(privateKey)
        agreement.doPhase(peerPublicKey, true)
        val sharedSecret = agreement.generateSecret()
        val salt = SESSION_KEY_SALT_LABEL.encodeToByteArray() + initiatorPublicKeyBytes + acceptorPublicKeyBytes
        return DirectionalSessionKeys(
            clientToServer = CryptoUtils.hkdfSha256(
                ikm = sharedSecret,
                salt = salt,
                info = CLIENT_TO_SERVER_INFO.encodeToByteArray(),
                length = 32,
            ),
            serverToClient = CryptoUtils.hkdfSha256(
                ikm = sharedSecret,
                salt = salt,
                info = SERVER_TO_CLIENT_INFO.encodeToByteArray(),
                length = 32,
            ),
        )
    }

    fun encrypt(key: ByteArray, counter: Long, plaintext: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce(counter)))
        return cipher.doFinal(plaintext)
    }

    fun decrypt(key: ByteArray, counter: Long, ciphertext: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, nonce(counter)))
        return cipher.doFinal(ciphertext)
    }

    private fun nonce(counter: Long): ByteArray {
        return ByteArray(4) + ByteBuffer.allocate(8).putLong(counter).array()
    }
}
