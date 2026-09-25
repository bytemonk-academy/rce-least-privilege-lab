package com.bytemonk.lab.recruit;

import java.util.UUID;

/** Basic checks on an uploaded resume. These reduce junk; they do not make a parser safe. */
public final class ResumeUpload {

    public static final int MAX_BYTES = 2 * 1024 * 1024;
    private static final byte[] PDF_MAGIC = {'%', 'P', 'D', 'F', '-'};

    private ResumeUpload() {
    }

    /** Returns an error message, or null if the file looks like a PDF we accept. */
    public static String validate(byte[] bytes) {
        if (bytes == null || bytes.length == 0) {
            return "resume is empty";
        }
        if (bytes.length > MAX_BYTES) {
            return "resume is larger than 2 MB";
        }
        if (bytes.length < PDF_MAGIC.length) {
            return "resume is not a PDF";
        }
        for (int i = 0; i < PDF_MAGIC.length; i++) {
            if (bytes[i] != PDF_MAGIC[i]) {
                return "resume is not a PDF";
            }
        }
        return null;
    }

    /** Server-chosen object key. Never build S3 keys from user input. */
    public static String newKey() {
        return "resumes/" + UUID.randomUUID() + ".pdf";
    }
}
