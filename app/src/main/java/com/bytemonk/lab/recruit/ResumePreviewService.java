package com.bytemonk.lab.recruit;

import java.io.IOException;
import java.util.Optional;

import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Extracts the first page of text so recruiters can preview a resume.
 *
 * TEACHING NOTE (this is the "PDF library bug" from the video, and it is hypothetical):
 * PDFBox is not known to have the bug described here. Imagine that the pinned version had
 * one, where a specially prepared PDF makes the parser run the attacker's instructions.
 *
 * Look at where this runs:
 *   1. Before login. ApplicationController calls it while handling a public upload.
 *   2. Inside the main app process, which holds the database password and the app's
 *      AWS credentials.
 * So an attacker would need no account, and their code would inherit this process's access.
 *
 * Fixes, in order: upgrade or replace the library; if no fix exists, turn previews off
 * (LAB_PREVIEW_ENABLED=false); and run parsing in a separate worker that has no database
 * password and no AWS permissions of its own.
 */
@Service
public class ResumePreviewService {

    private static final Logger log = LoggerFactory.getLogger(ResumePreviewService.class);
    private static final int MAX_PREVIEW_CHARS = 500;

    private final boolean enabled;

    public ResumePreviewService(LabProperties props) {
        this.enabled = props.preview().enabled();
    }

    public Optional<String> firstPageText(byte[] pdf) {
        if (!enabled) {
            return Optional.empty();
        }
        try (PDDocument document = Loader.loadPDF(pdf)) {
            PDFTextStripper stripper = new PDFTextStripper();
            stripper.setStartPage(1);
            stripper.setEndPage(1);
            String text = stripper.getText(document).strip();
            return Optional.of(text.length() > MAX_PREVIEW_CHARS ? text.substring(0, MAX_PREVIEW_CHARS) : text);
        } catch (IOException e) {
            log.warn("Could not build a preview: {}", e.getMessage());
            return Optional.empty();
        }
    }
}
