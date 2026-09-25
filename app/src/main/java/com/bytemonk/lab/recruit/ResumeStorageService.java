package com.bytemonk.lab.recruit;

import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

/**
 * Puts and gets resume PDFs in S3.
 *
 * Notice what is NOT here: no check of who the caller is. The recruiter check lives in
 * the web layer (SecurityConfig + ApplicationController). This service simply calls S3
 * with the application's credentials, so any code running inside this process can do
 * the same, including code an attacker manages to run.
 */
@Service
public class ResumeStorageService {

    private final S3Client s3;
    private final String bucket;

    public ResumeStorageService(S3Client s3, LabProperties props) {
        this.s3 = s3;
        this.bucket = props.storage().resumeBucket();
    }

    public void put(String key, byte[] pdf) {
        s3.putObject(PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .contentType("application/pdf")
                        .build(),
                RequestBody.fromBytes(pdf));
    }

    public byte[] get(String key) {
        // The AWS SDK signs this request with the app role's temporary credentials.
        // AWS sees a valid identity with s3:GetObject permission. It cannot tell whether
        // our controller or someone else's code asked for the file.
        return s3.getObjectAsBytes(GetObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build())
                .asByteArray();
    }
}
