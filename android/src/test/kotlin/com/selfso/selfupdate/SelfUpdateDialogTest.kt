/*
 * Copyright (C) 2026, Charles Chiou
 */

package com.selfso.selfupdate

import com.selfso.selfupdate.ui.formatBytes
import org.junit.Assert.assertEquals
import org.junit.Test

class SelfUpdateDialogTest {

    @Test
    fun testFormatBytes() {
        assertEquals("0 B", formatBytes(0L))
        assertEquals("0 B", formatBytes(-50L))
        assertEquals("500 B", formatBytes(500L))
        assertEquals("1.0 KB", formatBytes(1024L))
        assertEquals("1.5 KB", formatBytes(1536L))
        assertEquals("5.2 MB", formatBytes((5.2 * 1024 * 1024).toLong()))
        assertEquals("1.0 GB", formatBytes(1024L * 1024L * 1024L))
    }
}
