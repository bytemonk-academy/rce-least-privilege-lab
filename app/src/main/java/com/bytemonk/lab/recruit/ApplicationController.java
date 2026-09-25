package com.bytemonk.lab.recruit;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

/**
 * The request flow from the video.
 *
 *   POST /api/applications              public: a candidate applies and uploads a resume
 *   GET  /api/applications              recruiter only: list applications
 *   GET  /api/applications/{id}/resume  recruiter only: download a resume from S3
 *
 * Who may call what is enforced in SecurityConfig before these methods run.
 * That check protects this controller. It does not protect S3: the storage service
 * uses the application's own AWS identity.
 */
@RestController
@RequestMapping("/api/applications")
public class ApplicationController {

    private final ApplicationRepository applications;
    private final ResumeStorageService storage;
    private final ResumePreviewService preview;

    public ApplicationController(ApplicationRepository applications,
                                 ResumeStorageService storage,
                                 ResumePreviewService preview) {
        this.applications = applications;
        this.storage = storage;
        this.preview = preview;
    }

    /** Public endpoint. No login: anyone on the internet can reach this code. */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Map<String, Object>> apply(@RequestParam String name,
                                                     @RequestParam String email,
                                                     @RequestParam String position,
                                                     @RequestParam("resume") MultipartFile resume) throws IOException {
        byte[] pdf = resume.getBytes();
        String problem = ResumeUpload.validate(pdf);
        if (problem != null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, problem);
        }

        String key = ResumeUpload.newKey();
        storage.put(key, pdf);

        // The PDF library parses attacker-supplied bytes here, before any login.
        String previewText = preview.firstPageText(pdf).orElse(null);

        long id = applications.insert(name, email, position, key, previewText);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", id, "status", "received"));
    }

    @GetMapping
    public List<CandidateApplication> list() {
        return applications.findAll();
    }

    @GetMapping("/{id}/resume")
    public ResponseEntity<byte[]> resume(@PathVariable long id) {
        CandidateApplication application = applications.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        byte[] pdf = storage.get(application.resumeKey());
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, "inline; filename=\"resume-" + id + ".pdf\"")
                .body(pdf);
    }
}
