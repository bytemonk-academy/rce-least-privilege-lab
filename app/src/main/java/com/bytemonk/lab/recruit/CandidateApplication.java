package com.bytemonk.lab.recruit;

import java.time.OffsetDateTime;

/** One job application. The resume itself lives in S3; we store its key. */
public record CandidateApplication(
        long id,
        String name,
        String email,
        String position,
        String resumeKey,
        String resumePreview,
        OffsetDateTime submittedAt) {
}
