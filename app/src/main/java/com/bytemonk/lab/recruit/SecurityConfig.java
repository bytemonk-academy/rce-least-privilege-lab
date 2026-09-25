package com.bytemonk.lab.recruit;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

/**
 * The recruiter login. Deliberately simple (HTTP Basic, one in-memory user) so the lab
 * stays focused on the application's AWS permissions, not on login flows.
 *
 * MFA or a stronger login would protect the recruiter endpoints. It would not protect
 * the public upload endpoint, which runs before anyone signs in.
 */
@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(csrf -> csrf.disable()) // stateless JSON API, no browser session cookies
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        // Static pages. The recruiter page is public HTML; its data calls still need a login.
                        .requestMatchers(HttpMethod.GET, "/", "/index.html", "/recruiter.html",
                                "/assets/**", "/favicon.ico").permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/applications").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/applications", "/api/applications/**")
                        .hasRole("RECRUITER")
                        .requestMatchers("/error").permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    public UserDetailsService recruiters(PasswordEncoder encoder,
                                         @Value("${lab.recruiter.username}") String username,
                                         @Value("${lab.recruiter.password}") String password) {
        return new InMemoryUserDetailsManager(User.withUsername(username)
                .password(encoder.encode(password))
                .roles("RECRUITER")
                .build());
    }
}
