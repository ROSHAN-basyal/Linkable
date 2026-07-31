package com.linkable.contacts

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.provider.ContactsContract
import androidx.core.content.ContextCompat
import com.linkable.protocol.v1.PhoneContact
import com.linkable.protocol.v1.PhoneContactsRequest
import com.linkable.protocol.v1.PhoneContactsResponse
import com.linkable.protocol.v1.PhoneRecentContactsRequest
import com.linkable.protocol.v1.PhoneRecentContactsResponse
import com.linkable.protocol.v1.Timestamp

class PhoneContactsProvider(private val context: Context) {
    fun search(request: PhoneContactsRequest): PhoneContactsResponse {
        if (!hasContactsPermission()) {
            return PhoneContactsResponse.newBuilder()
                .setRequestId(request.requestId)
                .setSuccess(false)
                .setDetail("Grant Contacts permission on the phone.")
                .setCompletedAt(now())
                .build()
        }
        val contacts = queryContacts(request.query, request.limit.takeIf { it > 0 } ?: 20)
        return PhoneContactsResponse.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(true)
            .setDetail("Loaded ${contacts.size} contacts.")
            .addAllContacts(contacts)
            .setCompletedAt(now())
            .build()
    }

    fun recents(request: PhoneRecentContactsRequest): PhoneRecentContactsResponse {
        if (!hasCallLogPermission()) {
            return PhoneRecentContactsResponse.newBuilder()
                .setRequestId(request.requestId)
                .setSuccess(false)
                .setDetail("Grant Call Log permission on the phone.")
                .setCompletedAt(now())
                .build()
        }
        val contacts = queryRecentContacts(request.limit.takeIf { it > 0 } ?: 20)
        return PhoneRecentContactsResponse.newBuilder()
            .setRequestId(request.requestId)
            .setSuccess(true)
            .setDetail("Loaded ${contacts.size} recent contacts.")
            .addAllContacts(contacts)
            .setCompletedAt(now())
            .build()
    }

    private fun queryContacts(query: String, limit: Int): List<PhoneContact> {
        val trimmed = query.trim()
        if (trimmed.isBlank()) return emptyList()
        val uri = ContactsContract.CommonDataKinds.Phone.CONTENT_URI
        val projection = arrayOf(
            ContactsContract.CommonDataKinds.Phone.CONTACT_ID,
            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME_PRIMARY,
            ContactsContract.CommonDataKinds.Phone.NUMBER,
            ContactsContract.CommonDataKinds.Phone.LABEL,
            ContactsContract.CommonDataKinds.Phone.TYPE,
        )
        val selection = "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME_PRIMARY} LIKE ? OR ${ContactsContract.CommonDataKinds.Phone.NUMBER} LIKE ?"
        val args = arrayOf("%$trimmed%", "%$trimmed%")
        return buildList {
            context.contentResolver.query(uri, projection, selection, args, "${ContactsContract.CommonDataKinds.Phone.STARRED} DESC, ${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME_PRIMARY} ASC")?.use { cursor ->
                val id = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.CONTACT_ID)
                val name = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME_PRIMARY)
                val number = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.NUMBER)
                val label = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.LABEL)
                val type = cursor.getColumnIndexOrThrow(ContactsContract.CommonDataKinds.Phone.TYPE)
                while (cursor.moveToNext() && size < limit) {
                    add(
                        PhoneContact.newBuilder()
                            .setContactId(cursor.getString(id).orEmpty())
                            .setDisplayName(cursor.getString(name).orEmpty())
                            .setPhoneNumber(cursor.getString(number).orEmpty())
                            .setLabel(cursor.getString(label).orEmpty().ifBlank { phoneTypeLabel(cursor.getInt(type)) })
                            .build(),
                    )
                }
            }
        }
    }

    private fun queryRecentContacts(limit: Int): List<PhoneContact> {
        val projection = arrayOf(
            CallLog.Calls.CACHED_LOOKUP_URI,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.NUMBER,
            CallLog.Calls.TYPE,
            CallLog.Calls.DATE,
        )
        return buildList {
            context.contentResolver.query(CallLog.Calls.CONTENT_URI, projection, null, null, "${CallLog.Calls.DATE} DESC")?.use { cursor ->
                val id = cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_LOOKUP_URI)
                val name = cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NAME)
                val number = cursor.getColumnIndexOrThrow(CallLog.Calls.NUMBER)
                val type = cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE)
                val date = cursor.getColumnIndexOrThrow(CallLog.Calls.DATE)
                val seen = mutableSetOf<String>()
                while (cursor.moveToNext() && size < limit) {
                    val phoneNumber = cursor.getString(number).orEmpty()
                    if (phoneNumber.isBlank() || !seen.add(phoneNumber)) continue
                    add(
                        PhoneContact.newBuilder()
                            .setContactId(cursor.getString(id).orEmpty())
                            .setDisplayName(cursor.getString(name).orEmpty().ifBlank { phoneNumber })
                            .setPhoneNumber(phoneNumber)
                            .setLabel(callTypeLabel(cursor.getInt(type)))
                            .setLastInteractionEpochMs(cursor.getLong(date))
                            .build(),
                    )
                }
            }
        }
    }

    private fun phoneTypeLabel(type: Int): String {
        return when (type) {
            ContactsContract.CommonDataKinds.Phone.TYPE_MOBILE -> "Mobile"
            ContactsContract.CommonDataKinds.Phone.TYPE_HOME -> "Home"
            ContactsContract.CommonDataKinds.Phone.TYPE_WORK -> "Work"
            else -> "Phone"
        }
    }

    private fun callTypeLabel(type: Int): String {
        return when (type) {
            CallLog.Calls.INCOMING_TYPE -> "Incoming"
            CallLog.Calls.OUTGOING_TYPE -> "Outgoing"
            CallLog.Calls.MISSED_TYPE -> "Missed"
            else -> "Recent"
        }
    }

    private fun hasContactsPermission(): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) == PackageManager.PERMISSION_GRANTED
    }

    private fun hasCallLogPermission(): Boolean {
        return ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALL_LOG) == PackageManager.PERMISSION_GRANTED
    }

    private fun now(): Timestamp = Timestamp.newBuilder().setUnixEpochMs(System.currentTimeMillis()).build()
}
