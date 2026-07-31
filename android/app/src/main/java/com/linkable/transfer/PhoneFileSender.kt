package com.linkable.transfer

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import com.google.protobuf.ByteString
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.FileChunk
import com.linkable.protocol.v1.FileComplete
import com.linkable.protocol.v1.FileOffer
import com.linkable.protocol.v1.PacketType
import com.linkable.protocol.v1.Timestamp
import com.linkable.transport.ConnectionIO
import com.linkable.transport.EncryptedConnection
import java.security.MessageDigest
import java.io.File
import java.util.UUID

private data class FileMetadata(
    val fileName: String,
    val sizeBytes: Long,
    val sha256Hex: String,
    val mimeType: String,
)

class PhoneFileSender(
    private val context: Context,
) {
    fun send(
        encrypted: EncryptedConnection,
        uri: Uri,
        nextSequence: () -> Long,
        chunkSize: Int = 48 * 1024,
    ) {
        val metadata = metadata(uri)
        val transferId = UUID.randomUUID().toString()
        DebugEventLog.record("transfer", "Sending ${metadata.fileName} to desktop (${metadata.sizeBytes} bytes)")

        val offer = FileOffer.newBuilder()
            .setTransferId(transferId)
            .setFileName(metadata.fileName)
            .setSizeBytes(metadata.sizeBytes)
            .setSha256Hex(metadata.sha256Hex)
            .setMimeType(metadata.mimeType)
            .setChunkSize(chunkSize)
            .setOfferedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_FILE_OFFER,
                message = offer,
                sequenceNumber = nextSequence(),
            ),
        )

        var offset = 0L
        context.contentResolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(chunkSize)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                val chunk = FileChunk.newBuilder()
                    .setTransferId(transferId)
                    .setOffset(offset)
                    .setData(ByteString.copyFrom(buffer, 0, read))
                    .build()
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_FILE_CHUNK,
                        message = chunk,
                        sequenceNumber = nextSequence(),
                    ),
                )
                offset += read.toLong()
            }
        } ?: error("Unable to open selected file")

        val complete = FileComplete.newBuilder()
            .setTransferId(transferId)
            .setSha256Hex(metadata.sha256Hex)
            .build()
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_FILE_COMPLETE,
                message = complete,
                sequenceNumber = nextSequence(),
            ),
        )
        DebugEventLog.record("transfer", "Sent ${metadata.fileName}; waiting for desktop verification")
    }

    fun sendFile(
        encrypted: EncryptedConnection,
        file: File,
        nextSequence: () -> Long,
        chunkSize: Int = 48 * 1024,
    ) {
        require(file.isFile) { "Not a readable file: ${file.absolutePath}" }
        val metadata = metadata(file)
        val transferId = UUID.randomUUID().toString()
        DebugEventLog.record("transfer", "Sending ${metadata.fileName} from phone storage to desktop")
        val offer = FileOffer.newBuilder()
            .setTransferId(transferId)
            .setFileName(metadata.fileName)
            .setSizeBytes(metadata.sizeBytes)
            .setSha256Hex(metadata.sha256Hex)
            .setMimeType(metadata.mimeType)
            .setChunkSize(chunkSize)
            .setOfferedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_FILE_OFFER,
                message = offer,
                sequenceNumber = nextSequence(),
            ),
        )
        var offset = 0L
        file.inputStream().use { input ->
            val buffer = ByteArray(chunkSize)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                encrypted.writeEnvelope(
                    ConnectionIO.buildEnvelope(
                        packetType = PacketType.PACKET_TYPE_FILE_CHUNK,
                        message = FileChunk.newBuilder()
                            .setTransferId(transferId)
                            .setOffset(offset)
                            .setData(ByteString.copyFrom(buffer, 0, read))
                            .build(),
                        sequenceNumber = nextSequence(),
                    ),
                )
                offset += read.toLong()
            }
        }
        encrypted.writeEnvelope(
            ConnectionIO.buildEnvelope(
                packetType = PacketType.PACKET_TYPE_FILE_COMPLETE,
                message = FileComplete.newBuilder()
                    .setTransferId(transferId)
                    .setSha256Hex(metadata.sha256Hex)
                    .build(),
                sequenceNumber = nextSequence(),
            ),
        )
    }

    private fun metadata(uri: Uri): FileMetadata {
        val displayName = displayName(uri) ?: "linkable-transfer.bin"
        val mimeType = context.contentResolver.getType(uri) ?: "application/octet-stream"
        val digest = MessageDigest.getInstance("SHA-256")
        var size = 0L
        context.contentResolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
                size += read.toLong()
            }
        } ?: error("Unable to open selected file")
        return FileMetadata(
            fileName = displayName,
            sizeBytes = size,
            sha256Hex = digest.digest().joinToString("") { "%02x".format(it) },
            mimeType = mimeType,
        )
    }

    private fun metadata(file: File): FileMetadata {
        val digest = MessageDigest.getInstance("SHA-256")
        var size = 0L
        file.inputStream().use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
                size += read.toLong()
            }
        }
        return FileMetadata(
            fileName = file.name,
            sizeBytes = size,
            sha256Hex = digest.digest().joinToString("") { "%02x".format(it) },
            mimeType = android.webkit.MimeTypeMap.getSingleton()
                .getMimeTypeFromExtension(file.extension.lowercase())
                ?: "application/octet-stream",
        )
    }

    private fun displayName(uri: Uri): String? {
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (nameIndex >= 0 && cursor.moveToFirst()) {
                return cursor.getString(nameIndex)
            }
        }
        return uri.lastPathSegment?.substringAfterLast('/')
    }
}
