# RCE Blast Radius Lab: least privilege for a recruitment app

Companion project for the ByteMonk video **"FBI Cyberattack and Application Security"**.

A bug that lets an attacker run code is only half the story. The other half is what that code can reach. This lab gives you a small recruitment app, lets you give it too much AWS access, and then shows you exactly what changes when you apply least privilege.

You will:

1. Run a Spring Boot recruitment app (PostgreSQL for applications, S3 for resumes).
2. Give the app's IAM role a **broad** policy that also covers an HR employee archive.
3. Read a resume **and** an employee record using nothing but the app's credentials.
4. Switch to a **restricted** policy, repeat the identical test, and get `AccessDenied` for the archive.

Everything runs locally in Docker by default. No AWS account and no cloud cost. An optional path runs the same experiment against a real AWS sandbox account.

> **This repo contains no exploit.** The "vulnerable PDF library" is a teaching assumption. The lab tests *permissions*: what code running with the app's identity could reach after a compromise. See [Permission testing vs. an RCE exploit](#permission-testing-vs-an-rce-exploit).

---

## Architecture

```mermaid
flowchart LR
    C[Candidate<br/>no login] -->|POST /api/applications| APP
    R[Recruiter<br/>HTTP Basic] -->|GET /api/applications| APP
    subgraph APP[recruit-app process]
      CTRL[ApplicationController] --> STORE[ResumeStorageService]
      CTRL --> PREV[ResumePreviewService<br/>PDF parsing, pre-auth]
    end
    APP -->|app DB account| DB[(PostgreSQL)]
    APP -->|app IAM role<br/>temporary credentials| RB[(S3: resumes)]
    APP -. broad.json only .-> AB[(S3: HR employee archive)]
```

The recruiter's login protects the controller. It does not protect S3. Every S3 call the process makes is signed with the **app role's** temporary credentials, whichever class makes it. So the question that matters is: *what does that role allow?*

| Piece | Local (default) | Real AWS (optional) |
|---|---|---|
| App runtime | Docker container | Docker on EC2 |
| App identity | IAM role assumed through STS | Same role, via the EC2 instance profile |
| S3 + IAM + STS | [moto](https://github.com/getmoto/moto) emulator with IAM enforcement **on** | Your AWS sandbox account |
| Database | PostgreSQL container | PostgreSQL container |

---

## Quick start (local, about 5 minutes)

**You need:** Docker Desktop (or Docker Engine with the Compose plugin) and Git. Nothing else. Java and Python run inside containers.

```bash
git clone <this-repo-url> rce-least-privilege-lab
cd rce-least-privilege-lab

docker compose up -d --build     # first build downloads Maven dependencies, give it a few minutes
```

This starts PostgreSQL, the AWS emulator, runs the one-time lab setup (buckets, synthetic files, IAM role with the **broad** policy), and starts the app on <http://localhost:8080>.

### 1. Use the app like a normal user

Open <http://localhost:8080>, choose `fixtures/resumes/jane-candidate-resume.pdf`, and submit. No login needed: that is the public upload.

Then, as the recruiter:

```bash
curl -u recruiter:change-me-recruiter http://localhost:8080/api/applications
curl -u recruiter:change-me-recruiter -o resume.pdf http://localhost:8080/api/applications/1/resume
```

Without `-u` you get `401`. The controller's permission check works.

Or run all of that automatically:

```bash
scripts/smoke-test
```

### 2. Test what the app's identity can reach

```bash
scripts/check-access
```

Expected output with the broad policy:

```
Code running with the recruitment app's identity
  identity  arn:aws:sts::123456789012:assumed-role/rce-lab-recruit-app-role/check-access
  policy    infra/iam/broad.json
  No recruiter login and no controller checks: this calls S3 directly.

  ALLOWED  GetObject resume bucket     resumes/fixtures/jane-candidate-resume.pdf    859 bytes
  ALLOWED  GetObject employee archive  employees/employee-records-SYNTHETIC.csv      376 bytes
```

Both reads succeed. Both buckets are private, and it does not matter: *private* means the public cannot read them. The app's role can.

### 3. Apply least privilege and repeat the same test

```bash
scripts/use-policy restricted
scripts/check-access
```

```
  ALLOWED  GetObject resume bucket     resumes/fixtures/jane-candidate-resume.pdf    859 bytes
  DENIED   GetObject employee archive  employees/employee-records-SYNTHETIC.csv      AccessDenied
```

Same credentials source, same files, same requests. Only the policy changed.

Want the whole sequence in one go, with pass/fail checks? `scripts/demo`

### 4. Clean up

```bash
docker compose down -v
rm -rf .lab        # generated state (may need sudo on Linux, Docker created it)
```

> **Windows:** the `scripts/` files are Bash. Use Git Bash or WSL, or call the lab container directly: `docker compose run --rm lab check-access`, `docker compose run --rm lab use-policy restricted`.

---

## What to look at in the code

Follow three things, in this order. They are the same three shown in the video.

| File | What to notice |
|---|---|
| [`app/.../ApplicationController.java`](app/src/main/java/com/bytemonk/lab/recruit/ApplicationController.java) | The upload is public. The PDF preview runs on attacker-supplied bytes **before any login**. Recruiter endpoints are protected by [`SecurityConfig`](app/src/main/java/com/bytemonk/lab/recruit/SecurityConfig.java). |
| [`app/.../ResumeStorageService.java`](app/src/main/java/com/bytemonk/lab/recruit/ResumeStorageService.java) | `getObject` has no idea who the user is. It uses the app's credentials, which come from [`AwsConfig`](app/src/main/java/com/bytemonk/lab/recruit/AwsConfig.java). |
| [`infra/iam/broad.json`](infra/iam/broad.json) vs [`restricted.json`](infra/iam/restricted.json) | The only difference is the `HrIntegrationEmployeeArchive` statement. Object actions are scoped to object ARNs (`bucket/*`). |

Supporting pieces:

- [`app/.../ResumePreviewService.java`](app/src/main/java/com/bytemonk/lab/recruit/ResumePreviewService.java): the "vulnerable library" feature, with the teaching note and the fixes.
- [`lab/lab.py`](lab/lab.py): creates the lab resources and runs `check-access`. It assumes the app role (just like an EC2 instance profile would hand the app credentials) and calls S3 directly, skipping the controller entirely.
- [`fixtures/`](fixtures): a synthetic resume and a synthetic employee file. No real people.

---

## Experiments to try

Change the permissions and predict the result before you run `scripts/check-access`.

1. **Wildcard mistake.** In `broad.json`, replace both statements with one that allows `s3:GetObject` on `arn:aws:s3:::*`. Run `scripts/use-policy broad`. What else could the app read if more buckets existed?
2. **Write access.** Add `s3:PutObject` to the archive statement. Could a compromised app now tamper with employee records, not just read them?
3. **Explicit deny.** Keep the broad policy, but add a `Deny` statement for the archive bucket. Which wins?
4. **Turn off the risky feature.** Set `LAB_PREVIEW_ENABLED: "false"` in `docker-compose.yml`, run `docker compose up -d app`, and upload again. The application still works; the preview is simply empty. This is the "disable previews until a fix ships" option.
5. **Your own policy.** Create `infra/iam/mine.json` (use `${RESUME_BUCKET}` and `${ARCHIVE_BUCKET}` placeholders), then `scripts/use-policy mine`.

Reset at any time with `scripts/use-policy broad`.

---

## Optional: run against a real AWS account

The local emulator enforces IAM policies, but it is still an emulator. For real IAM enforcement, use a **dedicated sandbox account**. Never run labs in an account that holds production data.

**You need:** Python 3.9+, AWS credentials for the sandbox with permission to manage S3 buckets, IAM roles and instance profiles, and to call `sts:AssumeRole` (an admin user in a sandbox is fine).

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r lab/requirements.txt

export LAB_TARGET=aws
export AWS_PROFILE=my-sandbox      # or however you normally authenticate
export AWS_REGION=us-east-1

scripts/lab setup                           # buckets, synthetic files, role with broad.json
scripts/check-access --expect broad
scripts/use-policy restricted               # waits 15s for IAM to propagate
scripts/check-access --expect restricted
scripts/lab cleanup                         # deletes everything the lab created
```

What `setup` creates, all prefixed `rce-lab-`:

- Two private buckets with Block Public Access on: `rce-lab-resumes-<account>-<region>` and `rce-lab-hr-archive-<account>-<region>`
- Role `rce-lab-recruit-app-role`, trusted by EC2 and by identities in your account, with the inline policy `recruit-app-s3-access`
- Instance profile `rce-lab-recruit-app-profile`

`check-access` gets fresh temporary credentials each run (`sts:AssumeRole`), so a policy change is picked up without any caching on your side. IAM itself is eventually consistent; if a result looks stale, wait a few seconds and rerun. Credentials are never printed.

### Optional: run the app on EC2

This is the full setup from the video: the app on EC2, credentials from the instance profile.

1. Run `scripts/lab setup` as above and note `resume_bucket` from `scripts/lab status`.
2. Launch a small Amazon Linux 2023 instance. Under *Advanced details*, choose the IAM instance profile **rce-lab-recruit-app-profile** and set *Metadata response hop limit* to **2** (so containers can reach the instance metadata service with IMDSv2). Allow inbound TCP 8080 **from your IP only**.
3. On the instance:
   ```bash
   sudo dnf install -y docker git && sudo systemctl enable --now docker
   # install the Docker Compose plugin: https://docs.docker.com/compose/install/linux/
   git clone <this-repo-url> && cd rce-least-privilege-lab
   export AWS_REGION=us-east-1 LAB_RESUME_BUCKET=<resume_bucket> RECRUITER_PASSWORD=<pick-one>
   sudo -E docker compose -f docker-compose.aws.yml up -d --build
   ```
4. Use the app at `http://<instance-ip>:8080`, then run `scripts/use-policy restricted` from your laptop. Uploads still work. The app never needed the archive.
5. **Terminate the instance** when you are done, then run `scripts/lab cleanup`.

### Cost

| Item | Cost |
|---|---|
| Local lab | Free |
| IAM roles, instance profile, STS | Free |
| Two buckets with a few KB of synthetic files, a handful of requests | Fractions of a cent |
| Optional EC2 instance | A small instance is a few cents per hour. Check current [EC2 pricing](https://aws.amazon.com/ec2/pricing/on-demand/) and terminate it when finished |

---

## Permission testing vs. an RCE exploit

The video describes a hypothetical bug: a crafted PDF makes the preview library run the attacker's instructions (remote code execution). **This repo does not include that bug or any exploit.** PDFBox is used as a normal PDF library and is not known to have the flaw described.

Instead, `check-access` answers the question that decides the damage: *if someone could run code inside this app, what could it reach?* It does that by using the app role's credentials directly, exactly as injected code inside the process could. That is the part you can measure and fix in your own systems today.

Key points from the video, as they show up here:

- **Pre-authentication.** The preview runs during the public upload. Login and MFA protect the recruiter endpoints, not this code path.
- **Process permissions, not root.** The app container runs as a non-root user. Injected code starts with the app's rights: its IAM role and its database account.
- **Private and encrypted are not enough.** Both buckets are private and encrypted at rest. Neither stops a read by an identity that is allowed to read (and, with KMS, allowed to decrypt).
- **AWS cannot tell intent.** A request signed with valid credentials that the policy allows is allowed, whether our code or an attacker's made it.
- **Least privilege limits the damage; it does not fix the bug.** A compromised app can still read resumes it is allowed to read. Patch or replace the library, disable the feature if needed, and move PDF parsing into a separate worker that has no database password and no AWS permissions of its own.

### Check your own application

If someone could run code in your service, which files, tables and services could it reach? Look at the role attached to it, not the permissions of its users.

---

## About the FBI incident

The video uses a September 2026 report as its starting point. At the time of recording, the hacking group's claims (an Oracle PeopleSoft exploit, movement into systems on AWS GovCloud, the data volume) were **unverified**. Nothing in this repository is evidence about that incident; the app, the bug and the data are teaching examples.

Sources: [Reuters](https://www.reuters.com/world/hacked-fbi-data-has-sensitive-information-about-employees-intelligence-roles-2026-09-23/), [BleepingComputer](https://www.bleepingcomputer.com/news/security/shinyhunters-claims-fbi-hack-data-theft-in-peoplesoft-zero-day-breach/), [The Register](https://www.theregister.com/security/2026/09/22/shinyhunters-claims-fbi-hack-this-is-not-financially-motivated/5298385), [IAM roles for applications on EC2](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2.html), [S3 policy actions](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-with-s3-policy-actions.html), [AWS shared responsibility model](https://aws.amazon.com/compliance/shared-responsibility-model/).

---

## Repository layout

```
app/                     Spring Boot recruitment app (Java 21, Maven)
infra/iam/               broad.json, restricted.json, trust-policy.json
lab/lab.py               setup, check-access, use-policy, status, cleanup
fixtures/                synthetic resume PDF and synthetic employee CSV
scripts/                 check-access, use-policy, demo, smoke-test, lab
docker-compose.yml       local lab (Postgres, AWS emulator, setup, app)
docker-compose.aws.yml   optional: app on EC2 against real AWS
.github/workflows/ci.yml builds the app and runs the full experiment on every push
```

## Troubleshooting

- **Port 5000 already in use (macOS).** AirPlay Receiver uses it. Turn it off in System Settings > General > AirDrop & Handoff, or change `"5000:5000"` to `"5050:5000"` in `docker-compose.yml`. The containers talk to each other on the internal network either way.
- **The app fails with an STS or credentials error after restarting only the emulator.** The emulator keeps state in memory. Run `docker compose down && docker compose up -d` to recreate everything together.
- **`check-access` says "No lab state".** Run `docker compose up -d` (local) or `scripts/lab setup` (AWS) first.
- **Real AWS result looks stale after `use-policy`.** IAM changes can take a few seconds. Rerun `scripts/check-access`.

## License

MIT. Built by ByteMonk for learning. Use a sandbox, use synthetic data.
