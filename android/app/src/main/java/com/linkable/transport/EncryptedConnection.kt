package com.linkable.transport

import com.linkable.crypto.ReplayGuard
import com.linkable.crypto.SessionCipher
import com.linkable.protocol.v1.Envelope
import java.io.EOFException
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class EncryptedConnection(
    private val input: InputStream,
    private val output: OutputStream,
    private val sendKey: ByteArray,
    private val receiveKey: ByteArray,
    private val maxFrameSize: Int = 1_048_576,
) {
    private var sendCounter = 0L
    private val replayGuard = ReplayGuard()
    private val writeLock = Any()

    fun writeEnvelope(envelope: Envelope) {
        synchronized(writeLock) {
            val ciphertext = SessionCipher.encrypt(sendKey, sendCounter, envelope.toByteArray())
            val frame = ByteBuffer.allocate(8 + ciphertext.size)
                .order(ByteOrder.BIG_ENDIAN)
                .putLong(sendCounter)
                .put(ciphertext)
                .array()
            output.write(ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN).putInt(frame.size).array())
            output.write(frame)
            output.flush()
            sendCounter += 1
        }
    }

    fun readEnvelope(): Envelope {
        val header = readExact(4)
        val size = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN).int
        require(size in 9..maxFrameSize) { "Invalid encrypted frame size: $size" }
        val frame = readExact(size)
        val counter = ByteBuffer.wrap(frame, 0, 8).order(ByteOrder.BIG_ENDIAN).long
        replayGuard.checkAndMark(counter)
        val plaintext = SessionCipher.decrypt(receiveKey, counter, frame.copyOfRange(8, frame.size))
        return Envelope.parseFrom(plaintext)
    }

    private fun readExact(length: Int): ByteArray {
        val buffer = ByteArray(length)
        var read = 0
        while (read < length) {
            val count = input.read(buffer, read, length - read)
            if (count < 0) throw EOFException("Unexpected end of encrypted stream")
            read += count
        }
        return buffer
    }
}
