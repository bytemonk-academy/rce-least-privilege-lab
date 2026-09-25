package com.bytemonk.lab.recruit;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Settings under "lab.*" in application.yml.
 *
 * @param aws     how the app gets AWS credentials
 * @param storage where resumes live
 * @param preview the PDF preview feature (the "vulnerable" feature in the video)
 */
@ConfigurationProperties(prefix = "lab")
public record LabProperties(Aws aws, Storage storage, Preview preview) {

    /**
     * @param region              AWS region
     * @param endpoint            blank for real AWS, http://aws:5000 for the local emulator
     * @param roleArn             role to assume; blank means "use the default chain" (EC2 instance profile)
     * @param baseAccessKeyId     local emulator only: identity used to call sts:AssumeRole
     * @param baseSecretAccessKey local emulator only
     */
    public record Aws(String region, String endpoint, String roleArn,
                      String baseAccessKeyId, String baseSecretAccessKey) {
    }

    public record Storage(String resumeBucket) {
    }

    public record Preview(boolean enabled) {
    }
}
