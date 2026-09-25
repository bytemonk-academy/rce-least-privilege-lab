package com.bytemonk.lab.recruit;

import java.net.URI;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.util.StringUtils;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.checksums.RequestChecksumCalculation;
import software.amazon.awssdk.core.checksums.ResponseChecksumValidation;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;

/**
 * Where the application's AWS identity comes from.
 *
 * On EC2 the instance profile hands the app temporary credentials for its IAM role
 * (DefaultCredentialsProvider picks them up from the instance metadata service).
 * Locally we do the same thing explicitly: assume the role through STS.
 *
 * Either way, every S3 call the app makes, from any class, uses this one identity.
 * That identity, not the recruiter's login, is what AWS checks.
 */
@Configuration
public class AwsConfig {

    private static final Logger log = LoggerFactory.getLogger(AwsConfig.class);

    @Bean
    public AwsCredentialsProvider appCredentials(LabProperties props) {
        LabProperties.Aws aws = props.aws();
        if (!StringUtils.hasText(aws.roleArn())) {
            log.info("Using the default credentials chain (EC2 instance profile on AWS)");
            return DefaultCredentialsProvider.builder().build();
        }

        AwsCredentialsProvider base = StringUtils.hasText(aws.baseAccessKeyId())
                ? StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(aws.baseAccessKeyId(), aws.baseSecretAccessKey()))
                : DefaultCredentialsProvider.builder().build();

        var sts = StsClient.builder()
                .region(Region.of(aws.region()))
                .credentialsProvider(base);
        if (StringUtils.hasText(aws.endpoint())) {
            sts.endpointOverride(URI.create(aws.endpoint()));
        }

        log.info("Assuming app role {}", aws.roleArn());
        return StsAssumeRoleCredentialsProvider.builder()
                .stsClient(sts.build())
                .refreshRequest(r -> r.roleArn(aws.roleArn()).roleSessionName("recruit-app"))
                .build();
    }

    @Bean
    public S3Client s3Client(LabProperties props, AwsCredentialsProvider appCredentials) {
        LabProperties.Aws aws = props.aws();
        var builder = S3Client.builder()
                .region(Region.of(aws.region()))
                .credentialsProvider(appCredentials)
                .requestChecksumCalculation(RequestChecksumCalculation.WHEN_REQUIRED)
                .responseChecksumValidation(ResponseChecksumValidation.WHEN_REQUIRED);
        if (StringUtils.hasText(aws.endpoint())) {
            builder.endpointOverride(URI.create(aws.endpoint())).forcePathStyle(true);
        }
        return builder.build();
    }
}
