package com.bytemonk.lab.recruit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class ResumeUploadTest {

    @Test
    void acceptsPdfHeader() {
        assertNull(ResumeUpload.validate("%PDF-1.4 rest of file".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void rejectsNonPdf() {
        assertEquals("resume is not a PDF", ResumeUpload.validate("hello".getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    void rejectsEmptyAndOversized() {
        assertEquals("resume is empty", ResumeUpload.validate(new byte[0]));
        assertEquals("resume is larger than 2 MB", ResumeUpload.validate(new byte[ResumeUpload.MAX_BYTES + 1]));
    }

    @Test
    void keysAreServerChosen() {
        String key = ResumeUpload.newKey();
        assertTrue(key.startsWith("resumes/") && key.endsWith(".pdf"));
    }
}
