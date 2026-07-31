package com.linkable

import com.linkable.discovery.DirectConnectHelper
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DirectConnectHelperTest {
    @Test
    fun parsesHostAndPort() {
        val result = DirectConnectHelper.parse("192.168.0.5:9000")
        assertTrue(result.isSuccess)
        val candidate = result.getOrThrow()
        assertEquals("192.168.0.5", candidate.host)
        assertEquals(9000, candidate.port)
    }

    @Test
    fun usesDefaultPortWhenMissing() {
        val result = DirectConnectHelper.parse("192.168.0.5")
        assertTrue(result.isSuccess)
        assertEquals(7734, result.getOrThrow().port)
    }
}
