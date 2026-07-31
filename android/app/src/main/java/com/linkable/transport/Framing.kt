package com.linkable.transport

import com.google.protobuf.GeneratedMessageLite
import com.linkable.protocol.v1.Envelope
import com.linkable.protocol.v1.PacketType
import com.linkable.protocol.v1.ProtocolVersion
import java.io.EOFException
import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class ConnectionIO(
    private val input: InputStream,
    private val output: OutputStream,
) {
    fun readEnvelope(maxFrameSize: Int = 1_048_576): Envelope {
        val header = readExact(4)
        val size = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN).int
        require(size in 1..maxFrameSize) { "Invalid frame size: $size" }
        val payload = readExact(size)
        return Envelope.parseFrom(payload)
    }

    fun writeEnvelope(envelope: Envelope) {
        val bytes = envelope.toByteArray()
        output.write(ByteBuffer.allocate(4).order(ByteOrder.BIG_ENDIAN).putInt(bytes.size).array())
        output.write(bytes)
        output.flush()
    }

    private fun readExact(length: Int): ByteArray {
        val buffer = ByteArray(length)
        var read = 0
        while (read < length) {
            val count = input.read(buffer, read, length - read)
            if (count < 0) throw EOFException("Unexpected end of stream")
            read += count
        }
        return buffer
    }

    companion object {
        fun buildEnvelope(
            packetType: PacketType,
            message: GeneratedMessageLite<*, *>,
            sequenceNumber: Long,
        ): Envelope {
            val version = ProtocolVersion.newBuilder()
                .setMajor(1)
                .setMinor(0)
                .setPatch(0)
                .build()
            return Envelope.newBuilder()
                .setProtocolVersion(version)
                .setPacketType(packetType)
                .setSequenceNumber(sequenceNumber)
                .setPayload(message.toByteString())
                .build()
        }
    }
}
