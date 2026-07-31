package com.linkable.transfer

import android.Manifest
import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.annotation.RequiresApi
import com.linkable.LinkableApp
import com.linkable.debug.DebugEventLog
import com.linkable.protocol.v1.FileChunk
import com.linkable.protocol.v1.FileComplete
import com.linkable.protocol.v1.FileOffer
import com.linkable.protocol.v1.FileTransferResult
import com.linkable.protocol.v1.Timestamp
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap

private data class ActiveFileTransfer(
    val offer: FileOffer,
    val tempFile: File,
    val finalFile: File,
    var bytesReceived: Long = 0,
)

class FileTransferReceiver(
    private val context: Context,
) {
    private val activeTransfers = ConcurrentHashMap<String, ActiveFileTransfer>()

    fun handleOffer(offer: FileOffer): FileTransferResult {
        val directory = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: context.filesDir.resolve("downloads")
        directory.mkdirs()

        val safeName = safeFileName(offer.fileName)
        val tempFile = File(directory, "$safeName.${offer.transferId}.part")
        if (tempFile.exists()) tempFile.delete()
        activeTransfers[offer.transferId] = ActiveFileTransfer(
            offer = offer,
            tempFile = tempFile,
            finalFile = File(directory, safeName),
        )
        DebugEventLog.record("transfer", "Accepted ${offer.fileName} (${offer.sizeBytes} bytes)")
        showTransferNotification(
            title = "Receiving ${offer.fileName}",
            body = "${offer.sizeBytes} bytes from desktop",
        )
        return result(
            transferId = offer.transferId,
            success = true,
            detail = "accepted ${offer.fileName}",
            savedPath = "Linkable/${folderFor(offer)}/$safeName",
            bytesReceived = 0,
        )
    }

    fun handleChunk(chunk: FileChunk): FileTransferResult? {
        val transfer = activeTransfers[chunk.transferId] ?: return result(
            transferId = chunk.transferId,
            success = false,
            detail = "unknown transfer",
            savedPath = "",
            bytesReceived = 0,
        )
        if (chunk.offset != transfer.bytesReceived) {
            activeTransfers.remove(chunk.transferId)
            transfer.tempFile.delete()
            DebugEventLog.record("transfer", "Failed ${transfer.offer.fileName}: unexpected chunk offset")
            return result(
                transferId = chunk.transferId,
                success = false,
                detail = "unexpected chunk offset ${chunk.offset}, expected ${transfer.bytesReceived}",
                savedPath = transfer.finalFile.absolutePath,
                bytesReceived = transfer.bytesReceived,
            )
        }
        FileOutputStream(transfer.tempFile, true).use { output ->
            chunk.data.writeTo(output)
        }
        transfer.bytesReceived += chunk.data.size().toLong()
        return null
    }

    fun handleComplete(complete: FileComplete): FileTransferResult {
        val transfer = activeTransfers.remove(complete.transferId) ?: return result(
            transferId = complete.transferId,
            success = false,
            detail = "unknown transfer",
            savedPath = "",
            bytesReceived = 0,
        )
        if (transfer.bytesReceived != transfer.offer.sizeBytes) {
            transfer.tempFile.delete()
            DebugEventLog.record("transfer", "Failed ${transfer.offer.fileName}: size mismatch")
            return result(
                transferId = complete.transferId,
                success = false,
                detail = "size mismatch ${transfer.bytesReceived}/${transfer.offer.sizeBytes}",
                savedPath = transfer.finalFile.absolutePath,
                bytesReceived = transfer.bytesReceived,
            )
        }
        val actualSha = sha256Hex(transfer.tempFile)
        if (!actualSha.equals(complete.sha256Hex, ignoreCase = true)) {
            transfer.tempFile.delete()
            DebugEventLog.record("transfer", "Failed ${transfer.offer.fileName}: sha256 mismatch")
            return result(
                transferId = complete.transferId,
                success = false,
                detail = "sha256 mismatch",
                savedPath = transfer.finalFile.absolutePath,
                bytesReceived = transfer.bytesReceived,
            )
        }
        val savedPath = saveCompletedFile(transfer)
        transfer.tempFile.delete()
        DebugEventLog.record("transfer", "Received ${transfer.offer.fileName} -> $savedPath")
        showTransferNotification(
            title = "Received ${transfer.offer.fileName}",
            body = savedPath,
        )
        return result(
            transferId = complete.transferId,
            success = true,
            detail = "received ${transfer.offer.fileName}",
            savedPath = savedPath,
            bytesReceived = transfer.bytesReceived,
        )
    }

    private fun saveCompletedFile(transfer: ActiveFileTransfer): String {
        val folder = folderFor(transfer.offer)

        if (canWriteLinkableRootDirectly()) {
            runCatching {
                val linkableFolder = linkableRootDirectory().resolve(folder)
                linkableFolder.mkdirs()
                val publicFile = uniqueFile(linkableFolder, transfer.finalFile.name)
                transfer.tempFile.copyTo(publicFile, overwrite = true)
                return publicFile.absolutePath
            }.onFailure { error ->
                DebugEventLog.record("transfer", "Direct /Linkable save failed: ${error.message}")
            }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            runCatching {
                val uri = insertIntoPublicDownloads(transfer, folder)
                context.contentResolver.openOutputStream(uri, "w")?.use { output ->
                    transfer.tempFile.inputStream().use { input -> input.copyTo(output) }
                } ?: error("failed to open MediaStore output stream")
                markPublicDownloadReady(uri)
                return "Downloads/Linkable/$folder/${transfer.finalFile.name}"
            }.onFailure { error ->
                DebugEventLog.record("transfer", "MediaStore Linkable save failed: ${error.message}")
            }
        }

        runCatching {
            val linkableFolder = linkableRootDirectory().resolve(folder)
            linkableFolder.mkdirs()
            val publicFile = uniqueFile(linkableFolder, transfer.finalFile.name)
            transfer.tempFile.copyTo(publicFile, overwrite = true)
            return publicFile.absolutePath
        }.onFailure { error ->
            DebugEventLog.record("transfer", "Legacy /Linkable save failed: ${error.message}")
        }

        val fallbackDirectory = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: context.filesDir.resolve("downloads")
        fallbackDirectory.mkdirs()
        val fallbackFile = uniqueFile(fallbackDirectory, transfer.finalFile.name)
        transfer.tempFile.copyTo(fallbackFile, overwrite = true)
        return fallbackFile.absolutePath
    }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun insertIntoPublicDownloads(transfer: ActiveFileTransfer, folder: String): Uri {
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, transfer.finalFile.name)
            put(MediaStore.Downloads.MIME_TYPE, transfer.offer.mimeType.ifBlank { "application/octet-stream" })
            put(MediaStore.Downloads.IS_PENDING, 1)
            put(MediaStore.Downloads.RELATIVE_PATH, "${Environment.DIRECTORY_DOWNLOADS}/Linkable/$folder")
        }
        val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error("MediaStore insert returned null")
        return uri
    }

    private fun markPublicDownloadReady(uri: Uri) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return
        val values = ContentValues()
        values.clear()
        values.put(MediaStore.Downloads.IS_PENDING, 0)
        context.contentResolver.update(uri, values, null, null)
    }

    private fun result(
        transferId: String,
        success: Boolean,
        detail: String,
        savedPath: String,
        bytesReceived: Long,
    ): FileTransferResult {
        return FileTransferResult.newBuilder()
            .setTransferId(transferId)
            .setSuccess(success)
            .setDetail(detail)
            .setSavedPath(savedPath)
            .setBytesReceived(bytesReceived)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun safeFileName(fileName: String): String {
        val cleaned = fileName
            .substringAfterLast('/')
            .substringAfterLast('\\')
            .replace(Regex("[^A-Za-z0-9._ -]"), "_")
            .trim()
        return cleaned.ifBlank { "linkable-transfer.bin" }
    }

    private fun folderFor(offer: FileOffer): String {
        val fileName = offer.fileName.lowercase()
        val mimeType = offer.mimeType.lowercase()
        return when {
            mimeType.startsWith("image/") || fileName.hasAny(".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic") -> "images"
            mimeType.startsWith("video/") || fileName.hasAny(".mp4", ".mkv", ".mov", ".webm", ".3gp") -> "videos"
            mimeType == "application/pdf" || fileName.endsWith(".pdf") -> "pdfs"
            mimeType == "application/vnd.android.package-archive" || fileName.endsWith(".apk") -> "apks"
            else -> "files"
        }
    }

    private fun String.hasAny(vararg parts: String): Boolean = parts.any { contains(it) }

    private fun canWriteLinkableRootDirectly(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
            (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R && Environment.isExternalStorageManager())
    }

    @Suppress("DEPRECATION")
    private fun linkableRootDirectory(): File {
        return Environment.getExternalStorageDirectory().resolve("Linkable")
    }

    private fun uniqueFile(directory: File, fileName: String): File {
        val base = fileName.substringBeforeLast('.', fileName)
        val extension = fileName.substringAfterLast('.', "")
        var candidate = File(directory, fileName)
        var index = 1
        while (candidate.exists()) {
            val nextName = if (extension.isBlank()) {
                "$base-$index"
            } else {
                "$base-$index.$extension"
            }
            candidate = File(directory, nextName)
            index += 1
        }
        return candidate
    }

    private fun sha256Hex(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun showTransferNotification(title: String, body: String) {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            DebugEventLog.record("transfer", "Transfer notification skipped: notification permission missing")
            return
        }
        runCatching {
            val notification = NotificationCompat.Builder(context, LinkableApp.CONNECTION_CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_sys_upload_done)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setAutoCancel(true)
                .build()
            NotificationManagerCompat.from(context).notify(5201, notification)
        }.onFailure { error ->
            DebugEventLog.record("transfer", "Transfer notification failed: ${error.message}")
        }
    }
}
