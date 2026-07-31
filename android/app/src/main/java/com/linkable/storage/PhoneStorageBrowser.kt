package com.linkable.storage

import android.os.Environment
import android.webkit.MimeTypeMap
import com.linkable.protocol.v1.PhoneFileEntry
import com.linkable.protocol.v1.PhoneFileListRequest
import com.linkable.protocol.v1.PhoneFileListResponse
import com.linkable.protocol.v1.PhoneFilePullRequest
import com.linkable.protocol.v1.PhoneFilePullResult
import com.linkable.protocol.v1.Timestamp
import java.io.File

class PhoneStorageBrowser {
    private val root: File = Environment.getExternalStorageDirectory()

    fun list(request: PhoneFileListRequest): PhoneFileListResponse {
        val directory = resolveDirectory(request.path)
        if (directory == null) {
            return listResult(request, success = false, detail = "Path is outside phone storage.", entries = emptyList())
        }
        if (!directory.exists() || !directory.isDirectory) {
            return listResult(request, success = false, detail = "Folder not found or not accessible.", entries = emptyList())
        }
        val entries = directory.listFiles().orEmpty()
            .filter { !it.name.startsWith(".") }
            .sortedWith(compareBy<File> { !it.isDirectory }.thenBy { it.name.lowercase() })
            .take(250)
            .map { file ->
                PhoneFileEntry.newBuilder()
                    .setName(file.name)
                    .setPath(relativePath(file))
                    .setDirectory(file.isDirectory)
                    .setSizeBytes(if (file.isFile) file.length() else 0L)
                    .setMimeType(mimeType(file))
                    .setModifiedEpochMs(file.lastModified())
                    .build()
            }
        return listResult(request, success = true, detail = "Loaded ${entries.size} entries.", entries = entries)
    }

    fun fileFor(request: PhoneFilePullRequest): File? {
        val file = resolve(request.path) ?: return null
        return file.takeIf { it.exists() && it.isFile && it.canRead() }
    }

    fun pullResult(request: PhoneFilePullRequest, success: Boolean, detail: String): PhoneFilePullResult {
        return PhoneFilePullResult.newBuilder()
            .setRequestId(request.requestId)
            .setPath(request.path)
            .setSuccess(success)
            .setDetail(detail)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun listResult(
        request: PhoneFileListRequest,
        success: Boolean,
        detail: String,
        entries: List<PhoneFileEntry>,
    ): PhoneFileListResponse {
        return PhoneFileListResponse.newBuilder()
            .setRequestId(request.requestId)
            .setPath(request.path)
            .setSuccess(success)
            .setDetail(detail)
            .addAllEntries(entries)
            .setCompletedAt(Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build())
            .build()
    }

    private fun resolveDirectory(path: String): File? = resolve(path)?.takeIf { it.isDirectory || path.isBlank() }

    private fun resolve(path: String): File? {
        val candidate = if (path.isBlank() || path == "/") root else File(root, path.trimStart('/'))
        val canonicalRoot = root.canonicalFile
        val canonicalCandidate = candidate.canonicalFile
        return canonicalCandidate.takeIf { it.path == canonicalRoot.path || it.path.startsWith(canonicalRoot.path + File.separator) }
    }

    private fun relativePath(file: File): String {
        return file.canonicalFile.relativeTo(root.canonicalFile).path
    }

    private fun mimeType(file: File): String {
        if (file.isDirectory) return "inode/directory"
        return MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase())
            ?: "application/octet-stream"
    }
}
