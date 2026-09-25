package com.bytemonk.lab.recruit;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

/** PostgreSQL access. The app connects with its own database account, not the recruiter's. */
@Repository
public class ApplicationRepository {

    private static final RowMapper<CandidateApplication> ROW_MAPPER = (rs, rowNum) -> new CandidateApplication(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getString("email"),
            rs.getString("position"),
            rs.getString("resume_key"),
            rs.getString("resume_preview"),
            rs.getObject("submitted_at", OffsetDateTime.class));

    private final JdbcClient jdbc;

    public ApplicationRepository(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public long insert(String name, String email, String position, String resumeKey, String resumePreview) {
        return jdbc.sql("""
                        INSERT INTO candidate_application (name, email, position, resume_key, resume_preview)
                        VALUES (:name, :email, :position, :resumeKey, :resumePreview)
                        RETURNING id
                        """)
                .param("name", name)
                .param("email", email)
                .param("position", position)
                .param("resumeKey", resumeKey)
                .param("resumePreview", resumePreview)
                .query(Long.class)
                .single();
    }

    public List<CandidateApplication> findAll() {
        return jdbc.sql("SELECT * FROM candidate_application ORDER BY submitted_at DESC")
                .query(ROW_MAPPER)
                .list();
    }

    public Optional<CandidateApplication> findById(long id) {
        return jdbc.sql("SELECT * FROM candidate_application WHERE id = :id")
                .param("id", id)
                .query(ROW_MAPPER)
                .optional();
    }
}
