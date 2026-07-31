package com.linkable.crypto

import com.linkable.protocol.v1.PeerDescriptor
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.security.KeyPairGenerator
import java.security.spec.ECGenParameterSpec
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

object CryptoUtils {
    fun deriveDeviceId(publicKeyBytes: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(publicKeyBytes)
        return base32NoPadding(digest.copyOfRange(0, 10))
    }

    fun hkdfSha256(
        ikm: ByteArray,
        salt: ByteArray,
        info: ByteArray,
        length: Int,
    ): ByteArray {
        val saltKey = SecretKeySpec(salt, "HmacSHA256")
        val extractMac = Mac.getInstance("HmacSHA256").apply { init(saltKey) }
        val prk = extractMac.doFinal(ikm)

        var t = ByteArray(0)
        val output = ArrayList<Byte>()
        var counter = 1
        while (output.size < length) {
            val expandMac = Mac.getInstance("HmacSHA256").apply {
                init(SecretKeySpec(prk, "HmacSHA256"))
            }
            expandMac.update(t)
            expandMac.update(info)
            expandMac.update(counter.toByte())
            t = expandMac.doFinal()
            output.addAll(t.toList())
            counter += 1
        }
        return output.take(length).toByteArray()
    }

    fun derivePairingCode(
        pairingNonce: ByteArray,
        challengeNonce: ByteArray,
        initiatorPublicKey: ByteArray,
        acceptorPublicKey: ByteArray,
        codeLength: Int = 6,
    ): String {
        val raw = hkdfSha256(
            ikm = pairingNonce + challengeNonce,
            salt = initiatorPublicKey + acceptorPublicKey,
            info = "linkable-pair-code-v1".encodeToByteArray(),
            length = 8,
        )
        val value = raw.fold(0UL) { acc, byte -> (acc shl 8) + byte.toUByte().toULong() } % pow10(codeLength)
        return value.toString().padStart(codeLength, '0')
    }

    fun computeTranscriptHash(
        pairingNonce: ByteArray,
        challengeNonce: ByteArray,
        initiatorDeviceId: String,
        acceptorDeviceId: String,
        verificationCode: String,
    ): ByteArray {
        val digest = MessageDigest.getInstance("SHA-256")
        digest.update("PAIR_CONFIRM_V1".encodeToByteArray())
        digest.update(pairingNonce)
        digest.update(challengeNonce)
        digest.update(initiatorDeviceId.encodeToByteArray())
        digest.update(acceptorDeviceId.encodeToByteArray())
        digest.update(verificationCode.encodeToByteArray())
        return digest.digest()
    }

    fun buildSessionSignaturePayload(
        label: String,
        descriptor: PeerDescriptor,
        ephemeralPublicKey: ByteArray,
        issuedAtMs: Long,
    ): ByteArray {
        val output = ByteArrayOutputStream()
        writeLengthPrefixed(output, label.encodeToByteArray())
        writeLengthPrefixed(output, descriptor.deviceId.fingerprint.encodeToByteArray())
        writeLengthPrefixed(output, descriptor.deviceName.encodeToByteArray())
        writeLengthPrefixed(output, descriptor.platform.encodeToByteArray())
        writeLengthPrefixed(output, descriptor.identityPublicKey.toByteArray())
        writeLengthPrefixed(output, ephemeralPublicKey)
        output.write(ByteBuffer.allocate(8).putLong(descriptor.protocolVersion.major.toLong()).array())
        output.write(ByteBuffer.allocate(8).putLong(descriptor.protocolVersion.minor.toLong()).array())
        output.write(ByteBuffer.allocate(8).putLong(descriptor.protocolVersion.patch.toLong()).array())
        output.write(ByteBuffer.allocate(8).putLong(issuedAtMs).array())
        return output.toByteArray()
    }

    fun generateEphemeralPublicKeyBytes(): ByteArray {
        val generator = KeyPairGenerator.getInstance("EC")
        generator.initialize(ECGenParameterSpec("secp256r1"))
        return generator.generateKeyPair().public.encoded
    }

    fun isTimestampFresh(issuedAtMs: Long, maxSkewMs: Long, nowMs: Long = System.currentTimeMillis()): Boolean {
        return kotlin.math.abs(nowMs - issuedAtMs) <= maxSkewMs
    }

    private fun pow10(length: Int): ULong {
        var value = 1UL
        repeat(length) { value *= 10UL }
        return value
    }

    private fun writeLengthPrefixed(output: ByteArrayOutputStream, value: ByteArray) {
        output.write(ByteBuffer.allocate(4).putInt(value.size).array())
        output.write(value)
    }

    private fun base32NoPadding(input: ByteArray): String {
        val alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        val builder = StringBuilder((input.size * 8 + 4) / 5)
        var buffer = 0
        var bitsLeft = 0
        input.forEach { byte ->
            buffer = (buffer shl 8) or (byte.toInt() and 0xff)
            bitsLeft += 8
            while (bitsLeft >= 5) {
                val index = (buffer shr (bitsLeft - 5)) and 0x1f
                builder.append(alphabet[index])
                bitsLeft -= 5
            }
        }
        if (bitsLeft > 0) {
            val index = (buffer shl (5 - bitsLeft)) and 0x1f
            builder.append(alphabet[index])
        }
        return builder.toString()
    }
}
