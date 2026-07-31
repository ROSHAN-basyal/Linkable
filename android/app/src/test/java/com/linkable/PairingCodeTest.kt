package com.linkable

import com.linkable.crypto.CryptoUtils
import com.linkable.crypto.SessionCipher
import com.linkable.protocol.v1.DeviceId
import com.linkable.protocol.v1.PeerDescriptor
import com.linkable.protocol.v1.ProtocolVersion
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class PairingCodeTest {
    @Test
    fun deviceIdUsesStableBase32Alphabet() {
        val deviceId = CryptoUtils.deriveDeviceId(ByteArray(32) { 0x0A })
        assertTrue(deviceId.all { it in 'A'..'Z' || it in '2'..'7' })
    }

    @Test
    fun pairingCodeIsDeterministic() {
        val code1 = CryptoUtils.derivePairingCode(
            pairingNonce = ByteArray(32) { 0x01 },
            challengeNonce = ByteArray(32) { 0x02 },
            initiatorPublicKey = ByteArray(16) { 0x03 },
            acceptorPublicKey = ByteArray(16) { 0x04 },
        )
        val code2 = CryptoUtils.derivePairingCode(
            pairingNonce = ByteArray(32) { 0x01 },
            challengeNonce = ByteArray(32) { 0x02 },
            initiatorPublicKey = ByteArray(16) { 0x03 },
            acceptorPublicKey = ByteArray(16) { 0x04 },
        )
        assertEquals(code1, code2)
        assertEquals(6, code1.length)
    }

    @Test
    fun transcriptHashIsDeterministic() {
        val hash1 = CryptoUtils.computeTranscriptHash(
            pairingNonce = ByteArray(32) { 0x01 },
            challengeNonce = ByteArray(32) { 0x02 },
            initiatorDeviceId = "PHONE",
            acceptorDeviceId = "DESKTOP",
            verificationCode = "123456",
        )
        val hash2 = CryptoUtils.computeTranscriptHash(
            pairingNonce = ByteArray(32) { 0x01 },
            challengeNonce = ByteArray(32) { 0x02 },
            initiatorDeviceId = "PHONE",
            acceptorDeviceId = "DESKTOP",
            verificationCode = "123456",
        )
        assertArrayEquals(hash1, hash2)
    }

    @Test
    fun sessionSignaturePayloadIsDeterministic() {
        val descriptor = PeerDescriptor.newBuilder()
            .setDeviceId(DeviceId.newBuilder().setFingerprint("ABC123").build())
            .setDeviceName("Phone")
            .setPlatform("android")
            .setProtocolVersion(
                ProtocolVersion.newBuilder().setMajor(1).setMinor(0).setPatch(0).build(),
            )
            .setIdentityPublicKey(com.google.protobuf.ByteString.copyFrom(ByteArray(8) { 0x09 }))
            .build()
        val payload1 = CryptoUtils.buildSessionSignaturePayload(
            label = "linkable-session-init-v1",
            descriptor = descriptor,
            ephemeralPublicKey = ByteArray(16) { 0x06 },
            issuedAtMs = 1234L,
        )
        val payload2 = CryptoUtils.buildSessionSignaturePayload(
            label = "linkable-session-init-v1",
            descriptor = descriptor,
            ephemeralPublicKey = ByteArray(16) { 0x06 },
            issuedAtMs = 1234L,
        )
        assertArrayEquals(payload1, payload2)
    }

    @Test
    fun sessionDirectionalKeysMatchForBothSides() {
        val initiator = SessionCipher.generateEphemeralKeyPair()
        val acceptor = SessionCipher.generateEphemeralKeyPair()
        val initiatorKeys = SessionCipher.deriveDirectionalKeys(
            privateKey = initiator.privateKey,
            peerPublicKeyBytes = acceptor.publicKeyBytes,
            initiatorPublicKeyBytes = initiator.publicKeyBytes,
            acceptorPublicKeyBytes = acceptor.publicKeyBytes,
        )
        val acceptorKeys = SessionCipher.deriveDirectionalKeys(
            privateKey = acceptor.privateKey,
            peerPublicKeyBytes = initiator.publicKeyBytes,
            initiatorPublicKeyBytes = initiator.publicKeyBytes,
            acceptorPublicKeyBytes = acceptor.publicKeyBytes,
        )
        assertArrayEquals(initiatorKeys.clientToServer, acceptorKeys.clientToServer)
        assertArrayEquals(initiatorKeys.serverToClient, acceptorKeys.serverToClient)
    }
}
